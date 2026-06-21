"""Single-shot deep capture of both caliper signal lines from the DHO814.

Arms a single trigger on CH1 (clock) falling edge, waits for the next caliper packet,
then reads full raw acquisition memory for CH1 and CH2. Saves raw bytes + preamble to
disk for offline decode (decode_caliper.py).
"""
import sys
import time
from scope_lib import Scope

MDEPTH = 1_000_000          # points
TB_SCALE = 0.01             # s/div -> 100 ms window -> 1e6 pts / 0.1 s = 10 MSa/s
TRIG_LEVEL = 1.5            # V (midpoint of 0..3 V swing)


def read_raw(s, ch, maxchunk=250000):
    s.write(f":WAVeform:SOURce CHANnel{ch}")
    s.write(":WAVeform:MODE RAW")
    s.write(":WAVeform:FORMat BYTE")
    pre = s.query(":WAVeform:PREamble?")
    points = int(float(pre.split(",")[2]))
    data = bytearray()
    start = 1
    while start <= points:
        stop = min(start + maxchunk - 1, points)
        s.write(f":WAVeform:STARt {start}")
        s.write(f":WAVeform:STOP {stop}")
        blk = s.query_block(":WAVeform:DATA?")
        data += blk
        start = stop + 1
    return pre, bytes(data)


def main():
    s = Scope(timeout=20)
    print("IDN:", s.query("*IDN?"))

    # acquisition setup
    s.write(":RUN")
    s.write(f":ACQuire:MDEPth {MDEPTH}")
    s.write(":TIMebase:MAIN:MODE MAIN")
    s.write(f":TIMebase:MAIN:SCALe {TB_SCALE}")
    s.write(":TIMebase:MAIN:OFFSet 0")
    for ch in (1, 2):
        s.write(f":CHANnel{ch}:DISPlay ON")
        s.write(f":CHANnel{ch}:COUPling DC")
        s.write(f":CHANnel{ch}:SCALe 0.5")
        s.write(f":CHANnel{ch}:OFFSet -1.5")
    # trigger on clock (CH1) falling edge
    s.write(":TRIGger:MODE EDGE")
    s.write(":TRIGger:EDGE:SOURce CHANnel1")
    s.write(":TRIGger:EDGE:SLOPe NEGative")
    s.write(f":TRIGger:EDGE:LEVel {TRIG_LEVEL}")
    s.write(":TRIGger:SWEep NORMal")
    time.sleep(0.3)

    print("Arming single trigger...")
    s.write(":SINGle")
    time.sleep(0.2)

    # wait for trigger / acquisition complete
    deadline = time.time() + 15
    status = None
    while time.time() < deadline:
        status = s.query(":TRIGger:STATus?")
        if status == "STOP":
            break
        time.sleep(0.1)
    print("Trigger status:", status)

    srate = s.query(":ACQuire:SRATe?")
    mdep = s.query(":ACQuire:MDEPth?")
    print("Sample rate:", srate, "Mem depth:", mdep)

    for ch in (1, 2):
        pre, data = read_raw(s, ch)
        with open(f"cap_ch{ch}.bin", "wb") as f:
            f.write(data)
        with open(f"cap_ch{ch}.pre", "w") as f:
            f.write(pre)
        print(f"CH{ch}: {len(data)} bytes  preamble={pre}")

    s.screenshot("scope_capture.png")
    s.close()
    print("done")


if __name__ == "__main__":
    main()
