"""Reference decoder for the iGaging 35-065-U01 21-bit clock/data frame.

STATUS: HYPOTHESIS until bench-confirmed (see BRINGUP_PLAN.md phase 4-5). The reported
iGaging/Grizzly 21-bit encoding is:
    - 21 data bits, LSB-first, one's-complement signed (bit20 = sign)
    - value is RAW ABSOLUTE ENCODER TICKS, not the displayed number (no units/zero in stream)
    - scale ~= 4030 ticks/mm (~0.25 um/tick); CALIBRATE per-unit against gauge blocks

Once analyze_capture.py confirms the frame length, edge polarity, bit order, and sign
handling, lock the constants here and fill in `GROUND_TRUTH` with real (bitstring -> reading)
pairs so this doubles as a regression test and the source of truth for the MCU firmware port
(mirror of mxmoonfree_LS-20-6/caliper_decode.py).
"""
from dataclasses import dataclass

# --- to be pinned once bench-confirmed ---
FRAME_BITS = 21
LSB_FIRST = True
SIGN_ENCODING = "ones"          # "ones" | "twos"
TICKS_PER_MM = 4030.0           # PLACEHOLDER — calibrate against gauge blocks
MM_PER_INCH = 25.4


@dataclass
class Reading:
    ticks: int            # raw signed encoder count from the stream
    mm: float             # ticks / TICKS_PER_MM  (before any user zero offset)

    @property
    def inch(self):
        return self.mm / MM_PER_INCH

    def __str__(self):
        return f"{self.ticks:+d} ticks = {self.mm:+.4f} mm ({self.inch:+.5f} in)"


def _signed(bits):
    n = len(bits)
    val = sum(b << i for i, b in enumerate(bits))
    if bits[-1] == 1:
        if SIGN_ENCODING == "ones":
            val = -((~val) & ((1 << n) - 1))
        else:
            val -= (1 << n)
    return val


def decode_frame(bits):
    """bits: sequence of FRAME_BITS ints in wire order (LSB first if LSB_FIRST)."""
    if len(bits) != FRAME_BITS:
        raise ValueError(f"expected {FRAME_BITS} bits, got {len(bits)}")
    ordered = list(bits) if LSB_FIRST else list(reversed(bits))
    ticks = _signed(ordered)
    return Reading(ticks=ticks, mm=ticks / TICKS_PER_MM)


def decode_bitstring(s):
    return decode_frame([int(c) for c in s.strip()])


# Fill with confirmed (wire-order bitstring -> expected LCD reading) pairs during phase 5.
GROUND_TRUTH = {}


if __name__ == "__main__":
    if not GROUND_TRUTH:
        print("No ground-truth vectors captured yet — record them during bench phase 5.")
    for s, expect in GROUND_TRUTH.items():
        print(f"{s} -> {decode_bitstring(s)}   (expected {expect})")
