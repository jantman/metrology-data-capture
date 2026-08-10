"""Reference decoder for the Mitutoyo Digimatic (SPC) 52-bit frame.

Target instrument: Mitutoyo 500-171-30 ABSOLUTE Digimatic caliper (0-6"/150 mm,
0.0005"/0.01 mm) + Mitutoyo 959149 SPC connecting cable (1 m, with DATA-out switch,
10-pin Digimatic plug).

*** STATUS: DESK SPEC, NOT YET BENCH-VERIFIED ON THIS UNIT. ***
Everything below is assembled from published third-party implementations (see
README.md "Sources"), not from measurements of this caliper. Two conventions are
known to be reported inconsistently in the literature and are therefore handled
DEFENSIVELY here rather than assumed:

  1. Wire polarity. The CK/DATA outputs are open-collector; whether a logical 1 is
     a HIGH or a LOW on the wire depends on whose interface circuit you copy (a
     direct connection + pull-up inverts relative to a transistor-buffered one).
     `decode_frame()` resolves this from the frame itself: the first four nibbles
     are a constant 0xF preamble, so whichever polarity makes the preamble read
     0xFFFF is the correct one. See `Reading.inverted`.
  2. Sign nibble. Sources variously report nibble 5 as 0/8 or 0/1 for +/-, which is
     the same disagreement seen through a different within-nibble bit order. We
     treat ANY nonzero sign nibble as negative and record the raw value.

Frame (13 nibbles = 52 bits, nibble-wise, LSB of each nibble first):

  | nibble (1-based) | index | content                                        |
  |------------------|-------|------------------------------------------------|
  | 1-4              | 0-3   | preamble, all bits set (0xF each)              |
  | 5                | 4     | sign: 0 = positive, nonzero (8 or 1) = negative|
  | 6-11             | 5-10  | six BCD digits, most-significant digit first   |
  | 12               | 11    | decimal-point position = number of decimals    |
  | 13               | 12    | units: 0 = mm, 1 = inch                        |

  value = int(digits) / 10**dp, negated if the sign nibble is nonzero.

The decimal-point nibble is what makes a Digimatic frame self-describing: the tool
tells us where the point goes, so a 0.01 mm reading arrives as digits=000123 dp=2
("1.23") and an inch reading as digits=009840 dp=4 ("0.9840"). We format straight
from digits+dp rather than from the float, so the typed string matches the LCD
digit-for-digit (including trailing zeros) with no float rounding in the path.
"""
from dataclasses import dataclass, field

BITS_PER_FRAME = 52
NIBBLES_PER_FRAME = 13
PREAMBLE_NIBBLES = 4


class FrameError(ValueError):
    """Raised when a bit sequence cannot be a valid Digimatic frame."""


@dataclass
class Reading:
    value: float          # signed, in the unit reported by the frame
    unit: str             # "mm" or "in"
    text: str             # display-ready string, formatted from digits+dp (no float math)
    digits: str           # the six raw BCD digits, MSD first, as sent
    dp: int               # decimal-point position = number of decimal places
    negative: bool
    inverted: bool        # True if the wire polarity had to be flipped to find the preamble
    nibbles: list = field(default_factory=list)   # all 13 raw nibble values

    def __str__(self):
        return f"{self.text} {self.unit}"


def bits_to_nibbles(bits):
    """52 bits (in wire order) -> 13 nibble values, LSB of each nibble arriving first."""
    if len(bits) != BITS_PER_FRAME:
        raise FrameError(f"expected {BITS_PER_FRAME} bits, got {len(bits)}")
    out = []
    for n in range(NIBBLES_PER_FRAME):
        b = bits[4 * n:4 * n + 4]
        out.append(b[0] | (b[1] << 1) | (b[2] << 2) | (b[3] << 3))
    return out


def _format(digits, dp, negative):
    """Render digits+dp the way the LCD does: strip leading zeros, keep trailing ones."""
    if dp:
        ip, fp = digits[:-dp] or "0", digits[-dp:]
    else:
        ip, fp = digits, ""
    ip = ip.lstrip("0") or "0"
    sign = "-" if negative and int(digits) else ""     # never emit "-0.00"
    return f"{sign}{ip}.{fp}" if dp else f"{sign}{ip}"


def decode_frame(bits, polarity=None):
    """Decode 52 wire bits into a Reading.

    bits: sequence of 52 ints in the order they arrived on the wire.
    polarity: None (default) = infer from the preamble; True = bits are already
              logic-true; False = bits are inverted on the wire.

    Raises FrameError if the frame fails any structural check, which is what makes
    this safe to run on a free-running capture: garbage is rejected, not typed.
    """
    bits = [int(b) & 1 for b in bits]
    if len(bits) != BITS_PER_FRAME:
        raise FrameError(f"expected {BITS_PER_FRAME} bits, got {len(bits)}")

    candidates = [False, True] if polarity is None else [not polarity]
    for inverted in candidates:
        b = [1 - x for x in bits] if inverted else bits
        nib = bits_to_nibbles(b)
        if all(n == 0xF for n in nib[:PREAMBLE_NIBBLES]):
            break
    else:
        raise FrameError(
            "no 0xFFFF preamble in either polarity; "
            f"nibbles={''.join(f'{n:X}' for n in bits_to_nibbles(bits))}"
        )

    sign_nib = nib[4]
    digit_nibs = nib[5:11]
    dp = nib[11]
    unit_nib = nib[12]

    bad = [n for n in digit_nibs if n > 9]
    if bad:
        raise FrameError(f"non-BCD digit nibble(s) {bad} in {''.join(f'{n:X}' for n in nib)}")
    if dp > 6:
        raise FrameError(f"implausible decimal-point nibble {dp}")
    if unit_nib > 1:
        raise FrameError(f"implausible unit nibble {unit_nib}")

    digits = "".join(str(n) for n in digit_nibs)
    negative = sign_nib != 0
    unit = "in" if unit_nib == 1 else "mm"
    text = _format(digits, dp, negative)
    value = int(digits) / (10 ** dp)
    if negative:
        value = -value
    return Reading(value=value, unit=unit, text=text, digits=digits, dp=dp,
                   negative=negative, inverted=inverted, nibbles=nib)


def decode_bitstring(s, polarity=None):
    """s: 52-char '0'/'1' string in wire order."""
    return decode_frame([int(c) for c in s.strip()], polarity=polarity)


def encode_frame(digits, dp, unit, negative=False, sign_value=8, inverted=False):
    """Build a 52-bit wire frame. Used by the self-test and to generate scope-decode
    expectations; also documents the bit order by construction."""
    if len(digits) != 6 or not digits.isdigit():
        raise ValueError("digits must be exactly 6 decimal characters")
    nib = [0xF] * 4
    nib.append(sign_value if negative else 0)
    nib += [int(c) for c in digits]
    nib.append(dp)
    nib.append(1 if unit == "in" else 0)
    bits = []
    for n in nib:
        bits += [(n >> i) & 1 for i in range(4)]     # LSB of each nibble first
    return [1 - b for b in bits] if inverted else bits


if __name__ == "__main__":
    # ------------------------------------------------------------------
    # Self-test. NOTE: these vectors are SYNTHESIZED from the spec above, not
    # captured from the caliper -- they prove the bit arithmetic is self-consistent
    # and that polarity inference works, NOT that the spec matches this instrument.
    # Replace/extend with real captures once spc_capture.py has run (README step 4).
    # ------------------------------------------------------------------
    cases = [
        # (digits, dp, unit, negative, expected text)
        ("000000", 2, "mm", False, "0.00"),
        ("000123", 2, "mm", False, "1.23"),
        ("001000", 2, "mm", False, "10.00"),
        ("015000", 2, "mm", False, "150.00"),
        ("002000", 2, "mm", True,  "-20.00"),
        ("009840", 4, "in", False, "0.9840"),
        ("059055", 4, "in", True,  "-5.9055"),
    ]
    ok = True
    print("[selftest] round-tripping synthesized frames (both wire polarities):")
    for digits, dp, unit, neg, expect in cases:
        for inverted in (False, True):
            r = decode_frame(encode_frame(digits, dp, unit, neg, inverted=inverted))
            good = (r.text == expect and r.unit == unit and r.inverted == inverted)
            ok &= good
            print(f"  {'OK  ' if good else 'FAIL'} {'inv' if inverted else 'std'} "
                  f"{digits} dp={dp} {unit}{' neg' if neg else ''} -> {r.text:>10} "
                  f"(expect {expect})")

    # The sign-nibble ambiguity (8 vs 1) must not change the outcome.
    r1 = decode_frame(encode_frame("000500", 2, "mm", True, sign_value=1))
    r8 = decode_frame(encode_frame("000500", 2, "mm", True, sign_value=8))
    good = r1.text == r8.text == "-5.00"
    ok &= good
    print(f"  {'OK  ' if good else 'FAIL'} sign nibble 1 and 8 both read negative "
          f"({r1.text} / {r8.text})")

    # Structural rejection: a frame with no preamble must not decode in either polarity.
    try:
        decode_bitstring("0" * 26 + "1" * 26)
        print("  FAIL garbage frame decoded instead of raising")
        ok = False
    except FrameError:
        print("  OK   garbage frame rejected (no preamble in either polarity)")

    # Non-BCD digits must be rejected even with a valid preamble.
    bad = encode_frame("000000", 2, "mm")
    bad[5 * 4:5 * 4 + 4] = [1, 1, 1, 1]      # nibble 6 = 0xF, not a decimal digit
    try:
        decode_frame(bad)
        print("  FAIL non-BCD digit accepted")
        ok = False
    except FrameError:
        print("  OK   non-BCD digit nibble rejected")

    print("[selftest] ALL PASS" if ok else "[selftest] FAILURES PRESENT")
