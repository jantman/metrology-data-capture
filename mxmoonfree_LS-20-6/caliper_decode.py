"""Reference decoder for the Mxmoonfree LS-20 caliper 24-bit serial frame.

Protocol (confirmed 2026-06-21 against 5 known LCD readings):
  - 24-bit frame, LSB first, ~274 us/bit, new frame every ~107 ms.
  - Clock (Pin2) idles high, pulses low; DATA (Pin3) read on the clock RISING edge.
  - bits 0..19 = unsigned magnitude integer
  - bit 20    = sign (1 = negative)
  - bits 21,22 = unused (0)
  - bit 23    = unit flag (1 = inch, 0 = mm)
  - mm   value = magnitude / 100      (0.01 mm resolution)
  - inch value = magnitude / 2000     (0.0005 in resolution)

All signal levels are ~3 V referenced to Pin 5 (battery negative). The caliper body is
battery POSITIVE; do NOT connect Pin1/Pin4 to a logic input.
"""
from dataclasses import dataclass


@dataclass
class Reading:
    value: float        # in the displayed unit
    unit: str           # "mm" or "in"
    raw_magnitude: int
    negative: bool

    def __str__(self):
        return f"{self.value:+.4f} {self.unit}" if self.unit == "in" else f"{self.value:+.2f} {self.unit}"


def decode_frame(bits):
    """bits: sequence of 24 ints, LSB first (bit 0 first). Returns a Reading."""
    if len(bits) != 24:
        raise ValueError(f"expected 24 bits, got {len(bits)}")
    magnitude = sum(b << i for i, b in enumerate(bits[:20]))
    negative = bool(bits[20])
    is_inch = bool(bits[23])
    if is_inch:
        value = magnitude / 2000.0
        unit = "in"
    else:
        value = magnitude / 100.0
        unit = "mm"
    if negative:
        value = -value
    return Reading(value=value, unit=unit, raw_magnitude=magnitude, negative=negative)


def decode_bitstring(s):
    """s: 24-char '0'/'1' string, LSB first (e.g. '000010111110000000001000')."""
    return decode_frame([int(c) for c in s.strip()])


if __name__ == "__main__":
    # self-test against the ground-truth captures
    cases = {
        "000000000000000000000000": "+0.00 mm",
        "000101111100000000000000": "+10.00 mm",
        "000010001110010000000000": "+100.00 mm",
        "000010111110000000001000": "-20.00 mm",
        "000011011110000000000001": "+0.9840 in",
    }
    ok = True
    for s, expect in cases.items():
        got = str(decode_bitstring(s))
        flag = "OK" if got == expect else "FAIL"
        if flag == "FAIL":
            ok = False
        print(f"{flag}  {s}  -> {got:>12}  (expected {expect})")
    print("ALL PASS" if ok else "FAILURES PRESENT")
