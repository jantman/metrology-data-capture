"""Offline self-test for spc_capture.analyze() -- synthesize a Digimatic waveform and check
the capture pipeline decodes it.

Bench time with the caliper in one hand is the wrong place to discover that the analysis code
has an off-by-one in its edge extraction. This builds CK/DATA sample arrays exactly as the scope
would deliver them (idle-high open-collector clock, DATA valid before each falling edge),
including a deliberately inverted-polarity case and a two-press capture, then asserts that
analyze() recovers the right readings.

    python3 selftest_analyze.py
"""
import io

import numpy as np

from digimatic_decode import encode_frame
from spc_capture import analyze

XINC = 1e-7            # 100 ns/sample, in the ballpark of a 1 Mpt / 60 ms capture
BIT_US = 650.0         # published ~52 bits in ~34 ms
LOW_FRAC = 0.5         # clock spends half the bit low


def synth(frames, bit_us=BIT_US, idle_ms=100.0, gap_after_bit=None, gap_ms=0.0):
    """Build (datd, ckd) for a list of 52-bit wire frames, one frame per 'button press'.

    gap_after_bit/gap_ms optionally insert a longer intra-frame pause, so the test can prove that
    a real intra-frame gap does NOT get mistaken for a frame boundary.
    """
    spb = int(bit_us * 1e-6 / XINC)
    idle = int(idle_ms * 1e-3 / XINC)
    ck, dat = [np.ones(idle, dtype=np.int8)], [np.zeros(idle, dtype=np.int8)]
    for fi, bits in enumerate(frames):
        for i, b in enumerate(bits):
            nlow = int(spb * LOW_FRAC)
            ck.append(np.zeros(nlow, dtype=np.int8))          # CK asserted low: bit boundary
            ck.append(np.ones(spb - nlow, dtype=np.int8))
            dat.append(np.full(spb, b, dtype=np.int8))        # DATA stable across the whole bit
            if gap_after_bit is not None and i == gap_after_bit:
                pad = int(gap_ms * 1e-3 / XINC)
                ck.append(np.ones(pad, dtype=np.int8))
                dat.append(np.full(pad, b, dtype=np.int8))
        if fi != len(frames) - 1:                             # gap between two presses
            ck.append(np.ones(idle, dtype=np.int8))
            dat.append(np.zeros(idle, dtype=np.int8))
    ck.append(np.ones(idle, dtype=np.int8))
    dat.append(np.zeros(idle, dtype=np.int8))
    return np.concatenate(dat), np.concatenate(ck)


def run(name, frames, expect, **kw):
    datd, ckd = synth(frames, **kw)
    buf = io.StringIO()
    rows = analyze(datd, ckd, XINC, out=lambda *a: buf.write(" ".join(map(str, a)) + "\n"))
    got = [r[2] for r in rows if r[1] == "falling"]
    ok = got == expect
    print(f"  {'OK  ' if ok else 'FAIL'} {name}: {got}" + ("" if ok else f"  (expected {expect})"))
    if not ok:
        print(buf.getvalue())
    return ok


if __name__ == "__main__":
    print("[selftest] spc_capture.analyze() against synthesized waveforms:")
    ok = True

    # Baseline: one press, standard polarity.
    ok &= run("single frame, as-wired",
              [encode_frame("001234", 2, "mm")], ["12.34 mm"])

    # Inverted wire polarity -- what a direct open-collector connection most likely looks like.
    ok &= run("single frame, inverted",
              [encode_frame("009840", 4, "in", inverted=True)], ["0.9840 in"])

    # Negative, and a value near full travel.
    ok &= run("negative + full travel",
              [encode_frame("000250", 2, "mm", negative=True),
               encode_frame("014000", 2, "mm")],
              ["-2.50 mm", "140.00 mm"])

    # Two presses in one capture must split into two bursts, not one 104-bit run.
    ok &= run("two presses",
              [encode_frame("000100", 2, "mm"), encode_frame("000200", 2, "mm")],
              ["1.00 mm", "2.00 mm"])

    # A 3 ms intra-frame pause must stay INSIDE one burst (split threshold is 5 ms). This is the
    # failure mode that would silently halve a frame and produce "no decode" on real hardware.
    ok &= run("3 ms intra-frame gap tolerated",
              [encode_frame("000123", 2, "mm")], ["1.23 mm"],
              gap_after_bit=3, gap_ms=3.0)

    print("[selftest] ALL PASS" if ok else "[selftest] FAILURES PRESENT")
