"""Robust offline re-decode of all saved ground-truth captures.

For each bit cell (delimited by clock falling edges) sample DATA at a fixed fraction of the
bit period after the falling edge. Calibrate that fraction against the known magnitudes,
then report the full 24-bit frame (LSB-first) so high bits (sign, inch/mm flag) are visible.
"""
import glob, re
import numpy as np

CAPS = []  # (label, expect_mag, expect_neg)
KNOWN = {"0.00mm": (0, False), "10.00mm": (1000, False),
         "100.00mm": (10000, False), "-20.00mm": (2000, True)}

def load_pair(label):
    safe = "".join(c if c.isalnum() or c in "+-._" else "_" for c in label)
    dat = np.frombuffer(open(f"gt_{safe}_ch1.bin","rb").read(), np.uint8).astype(np.float64)
    clk = np.frombuffer(open(f"gt_{safe}_ch2.bin","rb").read(), np.uint8).astype(np.float64)
    return dat, clk

def digit(v):
    return (v > (v.min()+v.max())/2).astype(np.int8)

def first_burst_falls(clkd, xinc=160e-9, gap_s=2e-3):
    fall = np.where(np.diff(clkd) == -1)[0] + 1
    gap = gap_s/xinc
    burst = [fall[0]]
    for e in fall[1:]:
        if e - burst[-1] > gap:
            break
        burst.append(e)
    return np.array(burst)

def decode(label, frac=None):
    """Sample DATA just before each clock RISING edge (where the bit is valid)."""
    dat, clk = load_pair(label)
    datd, clkd = digit(dat), digit(clk)
    falls = first_burst_falls(clkd)
    rises = np.where(np.diff(clkd) == 1)[0] + 1
    bp = int(np.median(np.diff(falls)))
    margin = max(3, bp // 20)
    bits = []
    for f in falls:
        nxt = rises[rises > f]
        r = nxt[0] if len(nxt) else min(f + bp // 2, len(datd) - 1)
        bits.append(int(datd[max(0, r - margin)]))
    return bits, bp

def lsb_int(bits, n=None):
    bb = bits[:n] if n else bits
    v = 0
    for i, x in enumerate(bb):
        v |= (x << i)
    return v

labels = list(KNOWN.keys())
print(f"{'label':>10} | {'24 bits (LSB-first ->)':<26} | mag | exp | sign | b20 b21 b22 b23 | check")
for lab in labels:
    bits, bp = decode(lab)
    s = "".join(map(str, bits))
    mag = lsb_int(bits, 20)
    emag, eneg = KNOWN[lab]
    ok = (mag == emag) and ((bits[20] == 1) == eneg)
    print(f"{lab:>10} | {s:<26} | {mag:>5} | {emag:>5} | {'neg' if bits[20] else 'pos':>4} | "
          f"{bits[20]}   {bits[21]}   {bits[22]}   {bits[23]}   | {'OK' if ok else 'MISMATCH'}  (bp={bp*160e-9*1e6:.0f}us)")
