"""Reveal: decode the blind-captured positions A..F and print the readings.

Usage:  python3 reveal.py A B C D E F
"""
import sys
from decode_robust import decode
from caliper_decode import decode_frame

labels = sys.argv[1:] or ["A", "B", "C", "D", "E", "F"]
print(f"{'label':>6} | {'24-bit frame (LSB-first)':<26} | decoded reading")
print("-" * 60)
for lab in labels:
    bits, _ = decode(lab)
    r = decode_frame(bits)
    s = "".join(map(str, bits))
    print(f"{lab:>6} | {s:<26} | {r}")
