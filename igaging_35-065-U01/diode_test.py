"""CLOSED-CASE port health check — diode-test connector pins 1/2/3 against GND.

Purpose (review.md §4/§4.3): §11.7 drove the AWG's ~10 V EMF into every connector pin for a
session before the High-Z bug was found. The assessed damage risk is low, but it has never been
checked. This checks it WITHOUT opening the mic — everything is done through the Micro-USB
breakout, which exposes all five pins with the case closed.

WHAT WE ARE LOOKING FOR — it is a comparison, not an absolute number:
  * pins 2 and 3 are symmetric inputs (§11.15), so they should read ALIKE. A clear mismatch
    between them is the damage signature.
  * pin 1 lands on a transistor collector (inferred, §5.1a), so it is EXPECTED to read
    differently from 2/3. That is not damage — and if pin 1 instead reads like 2/3, that is
    itself interesting, because it would undercut the inferred topology.
  * a near-0 V reading / continuity beep in either direction = a shorted clamp = real damage.

*** BATTERY OUT for this test. *** A powered rail makes the readings meaningless (and the
forward direction would be injecting current into a live device).

Probe convention: the DMM sources current out of the RED lead. The informative direction is
RED on GND, BLACK on the signal pin, which forward-biases the pin's lower clamp diode
(anode = GND, cathode = pin). The reverse direction should be high/OL; a low reading there is
the alarm.

Run it yourself at the bench so you see the prompts live:

    ! python diode_test.py

Results are appended to findings/diode_test_<date>.txt for the bench log.
"""
import argparse
import datetime
import os
import sys

from dmm_lib import DMM

OUTDIR = "findings"

# (label, red lead, black lead, why)
STEPS = [
    ("pin4->pin5", "pin 4 (GND)", "pin 5 (GND)",
     "sanity: known short, should read ~0 / beep. If not, the breakout or leads are bad."),
    ("GND->pin1", "pin 4 (GND)", "pin 1", "forward clamp, pin 1 (the mic's output)"),
    ("GND->pin2", "pin 4 (GND)", "pin 2", "forward clamp, pin 2 (input)"),
    ("GND->pin3", "pin 4 (GND)", "pin 3", "forward clamp, pin 3 (input)  <-- compare with pin 2"),
    ("pin1->GND", "pin 1", "pin 4 (GND)", "reverse, pin 1 — expect high/OL"),
    ("pin2->GND", "pin 2", "pin 4 (GND)", "reverse, pin 2 — expect high/OL"),
    ("pin3->GND", "pin 3", "pin 4 (GND)", "reverse, pin 3 — expect high/OL"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-confirm", action="store_true",
                    help="don't ask for the battery-out confirmation (use if already verified)")
    args = ap.parse_args()

    d = DMM()
    print("DMM:", d.identify())

    if not args.skip_confirm:
        print("\n*** Is the BATTERY OUT of the micrometer, and the breakout connected? ***")
        if input("    type 'yes' to continue: ").strip().lower() not in ("y", "yes"):
            sys.exit("aborted — remove the battery first.")

    d.set_function("DIODE")
    print(f"meter set to DIODE mode (state: {d.state()})\n")

    results = {}
    for key, red, black, why in STEPS:
        print(f"--- {key} ---")
        print(f"    RED   -> {red}")
        print(f"    BLACK -> {black}")
        print(f"    ({why})")
        resp = input("    probes placed? [Enter to read / s to skip / q to quit] ").strip().lower()
        if resp == "q":
            break
        if resp == "s":
            results[key] = None
            print("    skipped\n")
            continue
        val, unit = d.read_settled(expect_function="DIODE")
        results[key] = val
        # XDM1041 reports ~overload as a very large value in diode mode.
        shown = "OL (open)" if abs(val) > 3.0 else f"{val:.4f} {unit}"
        print(f"    => {shown}\n")

    print("\n==== RESULTS ====")
    for key, _, _, _ in STEPS:
        v = results.get(key, "not run")
        if v is None:
            s = "skipped"
        elif v == "not run":
            s = "not run"
        else:
            s = "OL (open)" if abs(v) > 3.0 else f"{v:.4f} V"
        print(f"  {key:12} {s}")

    p2, p3 = results.get("GND->pin2"), results.get("GND->pin3")
    print("\n==== VERDICT ====")
    if isinstance(p2, float) and isinstance(p3, float):
        delta = abs(p2 - p3)
        print(f"  pin2 vs pin3 forward drop: {p2:.4f} V vs {p3:.4f} V  (delta {delta*1000:.1f} mV)")
        if delta < 0.030:
            print("  MATCHED -> no asymmetry between the symmetric inputs; no evidence of "
                  "over-drive damage on pins 2/3.")
        else:
            print("  *** MISMATCHED (>30 mV) -> this is the damage signature. Re-seat the probes "
                  "and repeat before believing it; if it holds, revisit review.md §4. ***")
    else:
        print("  pins 2/3 not both measured — inconclusive.")

    shorts = [k for k, v in results.items()
              if isinstance(v, float) and abs(v) < 0.05 and k != "pin4->pin5"]
    if shorts:
        print(f"  *** NEAR-SHORT on {shorts} -> blown clamp; real damage. ***")
    else:
        print("  No near-shorts on pins 1/2/3 in either direction.")

    os.makedirs(OUTDIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = f"{OUTDIR}/diode_test_{stamp}.txt"
    with open(path, "w") as f:
        f.write(f"OWON XDM1041 diode test, battery OUT, via Micro-USB breakout\n{stamp}\n\n")
        for key, red, black, why in STEPS:
            v = results.get(key, "not run")
            s = ("skipped" if v is None else "not run" if v == "not run"
                 else "OL" if abs(v) > 3.0 else f"{v:.4f} V")
            f.write(f"{key:12} RED={red:12} BLACK={black:12} {s}\n")
    print(f"\nsaved -> {path}")


if __name__ == "__main__":
    main()
