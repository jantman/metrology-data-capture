"""Is pin 1 an MCU output, or just the DATA button's contact wired to the connector?

WHY. §11.18 showed the button alone drives pin 1 low; strobe_end_capture then showed the low
lasts ~155 ms on a tap and **>3.2 s while the button is held** — i.e. it tracks the button rather
than being a fixed self-timed window. A switch contact brought out to the connector would explain
every observation at once: the ~0 V low (§11.18), the reading-independence (§11.16), the fact that
nothing ever shifts out of it, and why driving pin 1 does nothing (§11.15 — you would just be
fighting a closed switch).

THE DISCRIMINATOR — and it is decisive. **With the BATTERY OUT, a mechanical switch still
conducts. A transistor cannot.** So:

    battery out + button held + pin 1 reads a few ohms to GND   => mechanical switch contact
    battery out + button held + pin 1 stays open (~30 MOhm/OL)  => MCU-driven output, needs power

We already have half of this: §11.17b measured pin1->GND as OL with the battery out and the button
NOT pressed. This adds the other half.

Note the review.md §10.5 lead this would vindicate: in the reference Digimatic host design, the
cable's data pushbutton is part of the port interface rather than a private input to the tool.

*** BATTERY OUT. *** Breakout connected, DMM leads on pin 1 and pin 4.

    python button_switch_test.py

Readings are taken continuously for a few seconds per step and the MINIMUM is reported, so you
only have to hold the button during the window — no need to press Enter one-handed.
"""
import argparse
import datetime
import os
import time

from dmm_lib import DMM

FINDINGS = "findings"
SWITCH_MAX = 1000.0        # ohms; below this while unpowered = a closed contact


def sample_min(d, secs, label):
    """Poll for `secs` and return (min, median, n) — min is what matters for a contact."""
    vals = []
    t0 = time.time()
    while time.time() - t0 < secs:
        try:
            m = d.measurement()
            vals.append(m["value"])
        except Exception:
            pass
        time.sleep(0.15)
    if not vals:
        return None, None, 0
    s = sorted(vals)
    return s[0], s[len(s) // 2], len(vals)


def fmt(v):
    if v is None:
        return "no reading"
    return "OL (open)" if abs(v) > 5e7 else f"{v:,.1f} Ω"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secs", type=float, default=8.0, help="sampling window per step")
    ap.add_argument("--pin", type=int, default=1, choices=(1, 2, 3))
    args = ap.parse_args()

    d = DMM()
    print("DMM:", d.identify())
    print(f"\n*** BATTERY OUT of the micrometer. DMM leads on pin {args.pin} and pin 4 (GND). ***")
    print("    (polarity does not matter for a resistance measurement)")
    input("    press Enter when ready: ")

    d.set_function("RESISTANCE")
    print(f"meter in RESISTANCE mode ({d.state()})\n")

    print(f"[1/2] Button RELEASED — do not touch the mic. Sampling {args.secs:.0f}s...")
    rel_min, rel_med, rel_n = sample_min(d, args.secs, "released")
    print(f"      min {fmt(rel_min)}   median {fmt(rel_med)}   ({rel_n} samples)\n")

    print(f"[2/2] *** PRESS AND HOLD THE DATA BUTTON NOW *** for the next {args.secs:.0f}s...")
    time.sleep(1.0)
    hel_min, hel_med, hel_n = sample_min(d, args.secs, "held")
    print(f"      min {fmt(hel_min)}   median {fmt(hel_med)}   ({hel_n} samples)")
    print("      (you can let go)\n")

    print("==== VERDICT ====")
    print(f"  pin {args.pin} -> GND, battery OUT:")
    print(f"     released: {fmt(rel_min)}")
    print(f"     held:     {fmt(hel_min)}")
    verdict = None
    if hel_min is not None and hel_min < SWITCH_MAX:
        verdict = "switch"
        print(f"\n  *** MECHANICAL SWITCH CONTACT. *** pin {args.pin} conducts to ground while the")
        print("  button is held, with NO POWER APPLIED. A transistor cannot do that, so pin 1 is")
        print("  not an MCU output — the DATA button's contact is wired to the connector.")
        print("\n  Consequences: §11.15's \"pin 1 = the mic's sole OUTPUT\" is wrong in kind; the")
        print("  mic has NO output on the connector, and the measurement data must come out on")
        print("  pins 2/3. It also explains the ~0 V low, the reading-independence (§11.16), and")
        print("  why driving pin 1 does nothing. Vindicates the review.md §10.5 lead.")
    elif hel_min is not None and rel_min is not None and hel_min < rel_min / 10:
        verdict = "partial"
        print("\n  *** Resistance DROPPED with the button held but stayed high. Something is")
        print("  changing unpowered — possibly a switch in series with something, or leakage.")
        print("  Re-run, and try --pin 2 and --pin 3 as well. ***")
    else:
        verdict = "output"
        print("\n  NOT a bare switch: pin 1 stays open with the button held and no power. So the")
        print("  low seen in §11.18 requires the mic to be powered => pin 1 IS an MCU-driven")
        print("  output that mirrors the button, not a contact wired straight to the connector.")
        print("  §11.15's pin roles stand, and the ~155 ms / >3.2 s behaviour is firmware.")

    os.makedirs(FINDINGS, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = f"{FINDINGS}/button_switch_{stamp}.txt"
    with open(path, "w") as f:
        f.write(f"pin {args.pin} -> GND resistance, BATTERY OUT\n{stamp}\n\n")
        f.write(f"button released: min {fmt(rel_min)}  median {fmt(rel_med)}  n={rel_n}\n")
        f.write(f"button held:     min {fmt(hel_min)}  median {fmt(hel_med)}  n={hel_n}\n")
        f.write(f"\nverdict: {verdict}\n")
    print(f"\nsaved -> {path}")


if __name__ == "__main__":
    main()
