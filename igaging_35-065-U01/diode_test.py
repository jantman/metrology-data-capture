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

RUN IT IN A REAL TERMINAL (it prompts between probe placements):

    cd igaging_35-065-U01 && python diode_test.py

Everything printed is also teed, line by line, to `findings/diode_test_latest.txt` — a fixed
path, written incrementally, so the log survives an abort or a crash. A timestamped archive
copy is saved alongside it on completion.
"""
import argparse
import datetime
import os
import shutil
import sys

from dmm_lib import DMM

OUTDIR = "findings"
LOG_PATH = os.path.join(OUTDIR, "diode_test_latest.txt")

# (key, red lead, black lead, why)
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

_log_fh = None


def log(msg=""):
    """Print to the terminal AND append to the log file, flushed immediately."""
    print(msg)
    if _log_fh:
        _log_fh.write(msg + "\n")
        _log_fh.flush()
        os.fsync(_log_fh.fileno())


def ask(prompt):
    """Prompt on the terminal; echo both prompt and answer into the log."""
    try:
        ans = input(prompt)
    except EOFError:
        log(prompt + "  [EOF — no TTY]")
        raise SystemExit(
            "\nThis script prompts between probe placements, so it needs a real terminal.\n"
            "Run it directly:   cd igaging_35-065-U01 && python diode_test.py")
    if _log_fh:
        _log_fh.write(f"{prompt}{ans}\n")
        _log_fh.flush()
    return ans


def fmt(v):
    if v is None:
        return "skipped"
    if v == "not run":
        return "not run"
    return "OL (open)" if abs(v) > 3.0 else f"{v:.4f} V"


def main():
    global _log_fh
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-confirm", action="store_true",
                    help="don't ask for the battery-out confirmation (use if already verified)")
    args = ap.parse_args()

    os.makedirs(OUTDIR, exist_ok=True)
    _log_fh = open(LOG_PATH, "w")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    results = {}
    try:
        log("=" * 72)
        log(f"iGaging 35-065-U01 — closed-case diode test (battery OUT, via breakout)")
        log(f"started {stamp}")
        log("=" * 72)

        d = DMM()
        log(f"DMM: {d.identify()}")

        if not args.skip_confirm:
            log("\n*** Is the BATTERY OUT of the micrometer, and the breakout connected? ***")
            if ask("    type 'yes' to continue: ").strip().lower() not in ("y", "yes"):
                log("aborted — remove the battery first.")
                return

        d.set_function("DIODE")
        log(f"meter set to DIODE mode (state: {d.state()})\n")

        for key, red, black, why in STEPS:
            log(f"--- {key} ---")
            log(f"    RED   -> {red}")
            log(f"    BLACK -> {black}")
            log(f"    ({why})")
            resp = ask("    probes placed? [Enter to read / s to skip / q to quit] ").strip().lower()
            if resp == "q":
                log("    quit requested\n")
                break
            if resp == "s":
                results[key] = None
                log("    skipped\n")
                continue
            val, unit = d.read_settled(expect_function="DIODE")
            results[key] = val
            log(f"    => {fmt(val)}   (raw {val!r} {unit})\n")

        log("\n==== RESULTS ====")
        for key, _, _, _ in STEPS:
            log(f"  {key:12} {fmt(results.get(key, 'not run'))}")

        p2, p3 = results.get("GND->pin2"), results.get("GND->pin3")
        log("\n==== VERDICT ====")
        if isinstance(p2, float) and isinstance(p3, float):
            delta = abs(p2 - p3)
            log(f"  pin2 vs pin3 forward drop: {p2:.4f} V vs {p3:.4f} V  "
                f"(delta {delta * 1000:.1f} mV)")
            if delta < 0.030:
                log("  MATCHED -> no asymmetry between the symmetric inputs; no evidence of "
                    "over-drive damage on pins 2/3.")
            else:
                log("  *** MISMATCHED (>30 mV) -> this is the damage signature. Re-seat the "
                    "probes and repeat before believing it; if it holds, revisit review.md §4. ***")
        else:
            log("  pins 2/3 not both measured — inconclusive.")

        p1 = results.get("GND->pin1")
        if isinstance(p1, float) and isinstance(p2, float):
            log(f"  pin1 forward drop: {fmt(p1)}  (expected to DIFFER from pins 2/3 — it should "
                f"land on a transistor collector, not an MCU pin)")
            if abs(p1 - p2) < 0.030:
                log("  NOTE: pin 1 reads like the inputs. That is unexpected and would undercut "
                    "the inferred topology in review.md §5.1a — worth recording either way.")

        shorts = [k for k, v in results.items()
                  if isinstance(v, float) and abs(v) < 0.05 and k != "pin4->pin5"]
        if shorts:
            log(f"  *** NEAR-SHORT on {shorts} -> blown clamp; real damage. ***")
        else:
            log("  No near-shorts on pins 1/2/3 in either direction.")

    except KeyboardInterrupt:
        log("\n[interrupted by user — partial results above]")
    except Exception as e:
        log(f"\n[ERROR] {type(e).__name__}: {e}")
        raise
    finally:
        if _log_fh:
            _log_fh.write(f"\nfinished {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
            _log_fh.flush()
            _log_fh.close()
            _log_fh = None
        archive = os.path.join(
            OUTDIR, f"diode_test_{datetime.datetime.now():%Y-%m-%d_%H%M%S}.txt")
        try:
            shutil.copyfile(LOG_PATH, archive)
            print(f"\nlog -> {LOG_PATH}   (archive copy: {archive})")
        except OSError:
            print(f"\nlog -> {LOG_PATH}")


if __name__ == "__main__":
    main()
