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

def build_steps(refs):
    """Probe placements, ordered so the highest-value ones come first (you can quit early).

    refs: which ground pins to reference against, e.g. (4, 5). Referencing BOTH cross-checks
    the "pins 4 and 5 are the same node" assumption instead of taking it on faith.
    """
    steps = [("pin4-pin5", "pin 4 (GND)", "pin 5 (GND)",
              "ground integrity: known short. Proves current goes out pin 4, through the board, "
              "back pin 5 — i.e. BOTH ground pins are really contacting. If this is open, "
              "everything after it is meaningless.")]

    # HIGHEST VALUE, never tested before: are the signal pins separate nets at all?
    # If pins 2 and 3 are shorted, then §11.15's "two symmetric inputs, either one works" is
    # trivially true because they are ONE net — which would also collapse the three-signal-pin
    # count that the Digimatic argument leans on (review.md §10.3).
    for a, b in ((2, 3), (1, 2), (1, 3)):
        steps.append((f"pin{a}-pin{b}", f"pin {a}", f"pin {b}",
                      f"are pins {a} and {b} separate nets? A short here would be a major finding"))
        steps.append((f"pin{b}-pin{a}", f"pin {b}", f"pin {a}", "  (reverse direction)"))

    # Signal pins against each ground reference, both directions.
    for ref in refs:
        for pin in (1, 2, 3):
            note = "the mic's output" if pin == 1 else "input"
            steps.append((f"gnd{ref}-pin{pin}", f"pin {ref} (GND)", f"pin {pin}",
                          f"forward clamp, pin {pin} ({note})"
                          + ("  <-- compare with pin 2" if pin == 3 else "")))
        for pin in (1, 2, 3):
            steps.append((f"pin{pin}-gnd{ref}", f"pin {pin}", f"pin {ref} (GND)",
                          f"reverse, pin {pin} — expect high/OL"))
    return steps


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
    ap.add_argument("--refs", default="4,5",
                    help="ground pins to reference against (default 4,5 — cross-checks the "
                         "'pins 4 and 5 are the same node' assumption). Use '4' for a short run.")
    args = ap.parse_args()

    refs = tuple(int(x) for x in args.refs.split(","))
    steps = build_steps(refs)

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

        for key, red, black, why in steps:
            log(f"--- [{steps.index((key, red, black, why)) + 1}/{len(steps)}] {key} ---")
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
            UNIT = unit          # use the meter's own unit string ("Ω"), not a guess
            results[key] = val
            log(f"    => {fmt(val)}   (raw {val!r} {unit})\n")

        log("\n==== RESULTS ====")
        for key, _, _, _ in steps:
            log(f"  {key:12} {fmt(results.get(key, 'not run'))}")

        log("\n==== VERDICT ====")

        # NB: an overload reads as a ~1e9 sentinel, NOT a voltage. Comparing two sentinels
        # numerically yields a delta of 0.0 and a bogus "MATCHED" — guard every comparison.
        def is_ol(v):
            return isinstance(v, float) and abs(v) > OL_CUT

        def is_num(v):
            return isinstance(v, float) and abs(v) <= OL_CUT

        short_cut = 0.05 if args.mode == "diode" else 1000.0   # <1k Ohm is a real leakage path
        conducts = lambda v: is_num(v) and abs(v) < short_cut

        # --- 0. ground integrity ---------------------------------------------------------
        g = results.get("pin4-pin5")
        if conducts(g):
            log(f"  [ground] pin4-pin5 = {fmt(g)} -> both ground pins contact the board. Good.")
        elif g is not None and g != "not run":
            log(f"  *** [ground] pin4-pin5 = {fmt(g)} — NOT the short §11.3 recorded! Either a")
            log("      probe/breakout contact is bad or the ground bond has changed since the")
            log("      teardown. EVERYTHING BELOW IS SUSPECT until this is resolved. ***")

        # --- 1. are the signal pins separate nets? (never tested before) -------------------
        log("")
        pairs = [("pin2-pin3", "pin3-pin2", 2, 3), ("pin1-pin2", "pin2-pin1", 1, 2),
                 ("pin1-pin3", "pin3-pin1", 1, 3)]
        for fwd, rev, a, b in pairs:
            vf, vr = results.get(fwd), results.get(rev)
            vals = [v for v in (vf, vr) if isinstance(v, float)]
            if not vals:
                continue
            if any(conducts(v) for v in vals):
                log(f"  *** [nets] pin{a} and pin{b} CONDUCT ({fmt(vf)} / {fmt(vr)}) — they may be")
                log(f"      THE SAME NET. ***")
                if (a, b) == (2, 3):
                    log("      This would be a MAJOR finding: §11.15's \"pins 2 and 3 are symmetric")
                    log("      inputs, driving either works\" would be trivially true because there")
                    log("      is only ONE input. It would also collapse the three-signal-pin count")
                    log("      that the Digimatic argument leans on (review.md §10.3).")
            else:
                log(f"  [nets] pin{a} / pin{b}: {fmt(vf)} / {fmt(vr)} -> separate nets, not shorted.")

        # --- 2. cross-check the two ground references -------------------------------------
        log("")
        disagreements = []
        for pin in (1, 2, 3):
            for tmpl in (f"gnd{{}}-pin{pin}", f"pin{pin}-gnd{{}}"):
                v4, v5 = results.get(tmpl.format(4)), results.get(tmpl.format(5))
                if isinstance(v4, float) and isinstance(v5, float) and is_ol(v4) != is_ol(v5):
                    disagreements.append((tmpl.format("4/5"), v4, v5))
        if disagreements:
            log("  *** [refs] pin-4- and pin-5-referenced readings DISAGREE: ***")
            for k, v4, v5 in disagreements:
                log(f"      {k}: via pin4 {fmt(v4)} vs via pin5 {fmt(v5)}")
            log("      Pins 4 and 5 are NOT interchangeable as assumed. Re-seat and repeat.")
        else:
            _ref_reads = [v for k, v in results.items() if "gnd" in k and isinstance(v, float)]
            if _ref_reads and any(is_num(v) for v in _ref_reads):
                log("  [refs] pin-4- and pin-5-referenced readings agree -> the two ground pins")
                log("         are interchangeable, as §11.3 assumed. Verified, not taken on faith.")
            else:
                log("  [refs] every ground-referenced reading is OPEN, so pin-4 vs pin-5 agreement")
                log("         is VACUOUS (open == open proves nothing). The interchangeability")
                log("         assumption is NOT verified by this run — only the pin4-pin5 short is.")

        # --- 3. shorts to ground / damage --------------------------------------------------
        log("")
        gnd_reads = {k: v for k, v in results.items()
                     if ("gnd" in k) and isinstance(v, float)}
        gshorts = [k for k, v in gnd_reads.items() if conducts(v)]
        if gshorts:
            log(f"  *** [damage] NEAR-SHORT to ground on {gshorts} -> blown clamp; real damage. ***")
        else:
            log("  [damage] No short and no low-resistance path from any signal pin to ground, in")
            log("           either direction, against either ground pin.")
            log("           => rules out the COMMON over-voltage failure mode (a clamp fused short).")

        fwd = {p: results.get(f"gnd4-pin{p}") for p in (1, 2, 3)}
        if gnd_reads and all(is_ol(v) for v in gnd_reads.values()):
            log("\n  [damage] ALL signal-to-ground readings are OPEN in both directions.")
            log("  *** The pin2-vs-pin3 symmetry comparison therefore DID NOT RUN. *** With no")
            log("  working-clamp baseline there is nothing to compare against, so this CANNOT")
            log("  distinguish healthy protection structures from destroyed ones — only shorted")
            log("  ones (above). Damage is PARTIALLY addressed, not settled.")
            if args.mode == "diode":
                log("  Follow-up: re-run with --mode resistance, which measures into the MOhm range")
                log("  instead of stopping at the diode-test compliance voltage.")
            log("\n  Note on pin 1: open in BOTH directions is exactly what an open-collector NPN")
            log("  with a floating base does (battery out => base pulled nowhere). Mildly")
            log("  CONSISTENT with the inferred topology in review.md §5.1a, not against it.")
        elif is_num(fwd[2]) and is_num(fwd[3]):
            delta = abs(fwd[2] - fwd[3])
            log(f"\n  [damage] pin2 vs pin3 forward: {fwd[2]:.4f} vs {fwd[3]:.4f} {UNIT} "
                f"(delta {delta:.4f})")
            tol = 0.030 if args.mode == "diode" else max(fwd[2], fwd[3]) * 0.20
            if delta < tol:
                log("  MATCHED -> no asymmetry between the symmetric inputs; no evidence of")
                log("  over-drive damage on pins 2/3.")
            else:
                log("  *** MISMATCHED -> this is the damage signature. Re-seat the probes and")
                log("  repeat; if it holds, revisit review.md §4. ***")
            if is_ol(fwd[1]):
                log("  pin1 open while the inputs conduct -> consistent with pin 1 being a")
                log("  transistor collector rather than an MCU pin (review.md §5.1a).")
            elif is_num(fwd[1]):
                log(f"  pin1 forward: {fwd[1]:.4f} {UNIT} — expected to DIFFER from the inputs.")
                if abs(fwd[1] - fwd[2]) < tol:
                    log("  NOTE: pin 1 reads like the inputs — that would undercut the inferred")
                    log("  topology in review.md §5.1a. Worth recording either way.")
        elif isinstance(fwd[2], float) and isinstance(fwd[3], float) and is_ol(fwd[2]) != is_ol(fwd[3]):
            log(f"\n  *** [damage] ASYMMETRY: pin2 {fmt(fwd[2])} vs pin3 {fmt(fwd[3])} — one")
            log("  conducts and the other does not, on pins that should be symmetric inputs.")
            log("  Re-seat and repeat; if it holds, this is the damage signature (review.md §4). ***")

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
