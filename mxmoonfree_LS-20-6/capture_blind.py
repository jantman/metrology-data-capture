"""Blind capture: grab one frame for a labeled position, save raw samples, decode NOTHING.

Usage:  python3 capture_blind.py <LABEL>      e.g.  python3 capture_blind.py A

Saves gt_<LABEL>_ch1.bin (DATA) and gt_<LABEL>_ch2.bin (CLOCK). Prints only a structural
confirmation (clock-edge count) so the decoded reading stays hidden until reveal.py.
"""
import sys, time
import numpy as np
from scope_lib import Scope

label = sys.argv[1] if len(sys.argv) > 1 else "X"
safe = "".join(c if c.isalnum() or c in "+-._" else "_" for c in label)

s = Scope(timeout=30)
s.write(":RUN")
s.write(":ACQuire:MDEPth 1000000")
s.write(":TIMebase:MAIN:SCALe 0.01")
s.write(":TIMebase:MAIN:OFFSet 0")
for ch in (1, 2):
    s.write(f":CHANnel{ch}:DISPlay ON")
    s.write(f":CHANnel{ch}:COUPling DC")
    s.write(f":CHANnel{ch}:SCALe 0.5")
    s.write(f":CHANnel{ch}:OFFSet -1.5")
s.write(":TRIGger:MODE EDGE")
s.write(":TRIGger:EDGE:SOURce CHANnel2")
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
    s.query(":WAVeform:PREamble?")
    d = bytearray(); start = 1
    while start <= total:
        stop = min(start+mc-1, total)
        s.write(f":WAVeform:STARt {start}"); s.write(f":WAVeform:STOP {stop}")
        d += s.query_block(":WAVeform:DATA?"); start = stop+1
    return bytes(d)

d1 = read_raw(1, total)
d2 = read_raw(2, total)
open(f"gt_{safe}_ch1.bin", "wb").write(d1)
open(f"gt_{safe}_ch2.bin", "wb").write(d2)
s.close()

clk = np.frombuffer(d2, np.uint8).astype(np.float64)
clkd = (clk > (clk.min()+clk.max())/2).astype(np.int8)
fall = np.where(np.diff(clkd) == -1)[0] + 1
print(f"Captured '{label}': saved gt_{safe}_ch1.bin / gt_{safe}_ch2.bin "
      f"({len(fall)} clock falling edges total in window). Reading hidden until reveal.")
