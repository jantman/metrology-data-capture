"""Ground-truth capture: trigger on the caliper clock, grab one frame, decode 24 bits.

Usage:  python3 gt_capture.py "<label>"      e.g.  python3 gt_capture.py "0.00mm"

Triggers on CH2 (clock, pin2) falling edge, single-shot, reads both channels from deep
memory, samples DATA (CH1, pin3) at each clock edge, prints the bit pattern, and appends
a row to gt_log.csv for later mapping. Run once per known LCD reading.
"""
import sys, time, csv, os
import numpy as np
from scope_lib import Scope

label = sys.argv[1] if len(sys.argv) > 1 else "unlabeled"
safe = "".join(c if c.isalnum() or c in "+-._" else "_" for c in label)

s = Scope(timeout=30)
s.write(":RUN")
s.write(":ACQuire:MDEPth 1000000")
s.write(":TIMebase:MAIN:SCALe 0.01")     # ~160 ms window, ~6.25 MSa/s
s.write(":TIMebase:MAIN:OFFSet 0")
for ch in (1, 2):
    s.write(f":CHANnel{ch}:DISPlay ON")
    s.write(f":CHANnel{ch}:COUPling DC")
    s.write(f":CHANnel{ch}:SCALe 0.5")
    s.write(f":CHANnel{ch}:OFFSet -1.5")
s.write(":TRIGger:MODE EDGE")
s.write(":TRIGger:EDGE:SOURce CHANnel2")  # real clock
s.write(":TRIGger:EDGE:SLOPe NEGative")
s.write(":TRIGger:EDGE:LEVel 1.5")
s.write(":TRIGger:SWEep NORMal")
time.sleep(0.3)
s.write(":SINGle"); time.sleep(0.2)
dl = time.time() + 15; st = None
while time.time() < dl:
    st = s.query(":TRIGger:STATus?")
    if st == "STOP":
        break
    time.sleep(0.1)
if st != "STOP":
    print(f"!! no trigger (status={st}). Is the caliper on/transmitting?")
    s.close(); sys.exit(1)

total = int(float(s.query(":ACQuire:MDEPth?")))
def read_raw(ch, total, mc=200000):
    s.write(f":WAVeform:SOURce CHANnel{ch}"); s.write(":WAVeform:MODE RAW"); s.write(":WAVeform:FORMat BYTE")
    s.write(":WAVeform:STARt 1"); s.write(f":WAVeform:STOP {min(mc,total)}")
    pre = s.query(":WAVeform:PREamble?")
    d = bytearray(); start = 1
    while start <= total:
        stop = min(start+mc-1, total)
        s.write(f":WAVeform:STARt {start}"); s.write(f":WAVeform:STOP {stop}")
        d += s.query_block(":WAVeform:DATA?"); start = stop+1
    return pre, bytes(d)

pre1, d1 = read_raw(1, total)   # DATA pin3
pre2, d2 = read_raw(2, total)   # CLOCK pin2
open(f"gt_{safe}_ch1.bin", "wb").write(d1)
open(f"gt_{safe}_ch2.bin", "wb").write(d2)
xinc = float(pre2.split(",")[4])
s.close()

dat = np.frombuffer(d1, dtype=np.uint8).astype(np.float64)
clk = np.frombuffer(d2, dtype=np.uint8).astype(np.float64)
datd = (dat > (dat.min()+dat.max())/2).astype(np.int8)
clkd = (clk > (clk.min()+clk.max())/2).astype(np.int8)
fall = np.where(np.diff(clkd) == -1)[0] + 1
rise = np.where(np.diff(clkd) == 1)[0] + 1

# isolate first burst (falling edges spaced < 2 ms)
GAP = 2e-3 / xinc
burst = [fall[0]]
for e in fall[1:]:
    if e - burst[-1] > GAP:
        break
    burst.append(e)
burst = np.array(burst)
bits_f = [int(datd[i]) for i in burst]
# rising edges inside the burst span
rin = rise[(rise >= burst[0]-2) & (rise <= burst[-1]+2)]
bits_r = [int(datd[i]) for i in rin]

sf = "".join(map(str, bits_f))
sr = "".join(map(str, bits_r))

def as_int(bits, lsb_first):
    b = bits[::-1] if lsb_first else bits
    v = 0
    for x in b:
        v = (v << 1) | x
    return v

print(f"\n=== {label} ===  ({len(burst)} clock falling edges)")
print(f"  DATA @ falling: {sf}")
print(f"  DATA @ rising : {sr}")
for nm, bb in (("falling", bits_f), ("rising", bits_r)):
    print(f"  [{nm}] LSB-first int={as_int(bb, True):>10}  MSB-first int={as_int(bb, False):>10}")

newfile = not os.path.exists("gt_log.csv")
with open("gt_log.csv", "a", newline="") as f:
    w = csv.writer(f)
    if newfile:
        w.writerow(["label", "n_edges", "bits_falling", "bits_rising"])
    w.writerow([label, len(burst), sf, sr])
print("  logged to gt_log.csv")
