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


# Overload sentinel from the meter (~1e9). In diode mode a real reading is a forward drop of a
# volt or two; in resistance mode a real reading can legitimately be megohms, so the "is this an
# overload?" cut differs per mode. Set by main() before any formatting happens.
OL_CUT = 3.0
UNIT = "V"


def fmt(v):
    if v is None:
        return "skipped"
    if v == "not run":
        return "not run"
    return "OL (open)" if abs(v) > OL_CUT else f"{v:.4f} {UNIT}"


def main():
    global _log_fh
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-confirm", action="store_true",
                    help="don't ask for the battery-out confirmation (use if already verified)")
    ap.add_argument("--mode", choices=("diode", "resistance"), default="diode",
                    help="diode: forward-drop test (default). resistance: measures into the MOhm "
                         "range, so it sees a partial/leaky path that reads OL in diode mode — "
                         "use this as the follow-up when diode mode comes back all-open.")
    args = ap.parse_args()

    global OL_CUT, UNIT
    OL_CUT = 3.0 if args.mode == "diode" else 5e7   # 50 MOhm: above this the meter is open
    UNIT = "V" if args.mode == "diode" else "Ohm"

    os.makedirs(OUTDIR, exist_ok=True)
    _log_fh = open(LOG_PATH, "w")
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    results = {}
    try:
        log("=" * 72)
        log(f"iGaging 35-065-U01 — closed-case port health check ({args.mode} mode), battery OUT, via breakout")
        log(f"started {stamp}")
        log("=" * 72)

        d = DMM()
        log(f"DMM: {d.identify()}")

        if not args.skip_confirm:
            log("\n*** Is the BATTERY OUT of the micrometer, and the breakout connected? ***")
            if ask("    type 'yes' to continue: ").strip().lower() not in ("y", "yes"):
                log("aborted — remove the battery first.")
                return

        func = "DIODE" if args.mode == "diode" else "RESISTANCE"
        d.set_function(func)
        log(f"meter set to {func} mode (state: {d.state()})\n")

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
            val, unit = d.read_settled(expect_function=func)
            results[key] = val
            log(f"    => {fmt(val)}   (raw {val!r} {unit})\n")

        log("\n==== RESULTS ====")
        for key, _, _, _ in STEPS:
            log(f"  {key:12} {fmt(results.get(key, 'not run'))}")

        p1 = results.get("GND->pin1")
        p2, p3 = results.get("GND->pin2"), results.get("GND->pin3")
        log("\n==== VERDICT ====")

        # NB: an overload reads as a ~1e9 sentinel, NOT a voltage. Comparing two sentinels
        # numerically yields a delta of 0.0 and a bogus "MATCHED" — guard every comparison.
        def is_ol(v):
            return isinstance(v, float) and abs(v) > OL_CUT

        def is_num(v):
            return isinstance(v, float) and abs(v) <= OL_CUT

        signal_reads = {k: v for k, v in results.items() if k != "pin4->pin5"}
        measured = [v for v in signal_reads.values() if is_num(v)]

        short_cut = 0.05 if args.mode == "diode" else 1000.0   # <1k Ohm is a real leakage path
        shorts = [k for k, v in signal_reads.items() if is_num(v) and abs(v) < short_cut]
        if shorts:
            log(f"  *** NEAR-SHORT on {shorts} -> blown clamp; real damage. ***")
        else:
            log("  No shorts and no low-resistance path from any signal pin to ground, in "
                "either direction.")
            log("  => rules out the COMMON over-voltage failure mode (a clamp fused short).")

        if not measured and all(is_ol(v) for v in signal_reads.values()):
            log("\n  ALL signal-pin readings are OPEN (OL) in both directions.")
            log("  *** The pin2-vs-pin3 symmetry comparison therefore DID NOT RUN. *** There is")
            log("  no working-clamp baseline to compare against, so this test CANNOT distinguish")
            log("  healthy protection structures from destroyed ones — only shorted ones (above).")
            log("  Treat the damage question as PARTIALLY addressed, not settled.")
            log("  Follow-up that would tighten it: re-run in RESISTANCE mode (--mode resistance),")
            log("  which measures into the MOhm range instead of stopping at the diode-test")
            log("  compliance voltage, and can see a partial/leaky path that reads OL here.")
            log("\n  Note on pin 1: open in BOTH directions is exactly what an open-collector NPN")
            log("  with a floating base does (battery out => base pulled nowhere). That is mildly")
            log("  CONSISTENT with the inferred topology in review.md §5.1a, not against it.")
        elif is_num(p2) and is_num(p3):
            delta = abs(p2 - p3)
            log(f"  pin2 vs pin3 forward drop: {p2:.4f} V vs {p3:.4f} V  "
                f"(delta {delta * 1000:.1f} mV)")
            if delta < 0.030:
                log("  MATCHED -> no asymmetry between the symmetric inputs; no evidence of "
                    "over-drive damage on pins 2/3.")
            else:
                log("  *** MISMATCHED (>30 mV) -> this is the damage signature. Re-seat the "
                    "probes and repeat before believing it; if it holds, revisit review.md §4. ***")
            if is_num(p1):
                log(f"  pin1 forward drop: {p1:.4f} V (expected to DIFFER from the inputs — it "
                    f"should land on a transistor collector, not an MCU pin)")
                if abs(p1 - p2) < 0.030:
                    log("  NOTE: pin 1 reads like the inputs — that would undercut the inferred "
                        "topology in review.md §5.1a. Worth recording either way.")
            elif is_ol(p1):
                log("  pin1: open, while the inputs conduct -> consistent with pin 1 being a "
                    "transistor collector rather than an MCU pin (review.md §5.1a).")
        elif is_ol(p2) != is_ol(p3):
            log(f"  *** ASYMMETRY: pin2 {fmt(p2)} vs pin3 {fmt(p3)} — one conducts and the other")
            log("  does not, on pins that are supposed to be symmetric inputs. Re-seat the probes")
            log("  and repeat; if it holds, this is the damage signature (review.md §4). ***")
        else:
            log("  pins 2/3 not both measured — inconclusive.")

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
