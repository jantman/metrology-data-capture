"""Measure pin 1's strobe from END to END — the length nobody has ever actually measured.

THE PROBLEM. Every capture of the pin-1 strobe has put the trigger at CENTRE screen
(`:TIMebase:MAIN:OFFSet 0`), so only half the record is post-trigger and the pin is still low
when acquisition stops. "~10 ms" (§11.14), "~10 ms" (§11.15), "~25 ms" (§11.16) and "24.95 ms"
(§11.18) are all just half-a-record — floors, not measurements (review.md §1.2). The rising edge
has never been seen.

THE FIX. Put the trigger at the far LEFT via a positive horizontal offset (~5 divisions on the
DHO814's 10-division screen), so the record is almost entirely post-trigger, and widen the window
until the rising edge appears. This auto-escalates the window until the strobe ends or the ceiling
is hit.

THE SECOND QUESTION, which matters for what comes next: does the strobe end **on its own** after a
fixed time, or when the **button is released**? That decides whether pin 1 is a timed data-ready
window or simply a mirror of the button contact — and it decides how a gated clock burst has to be
timed. So this runs two phases:

    phase TAP  — press and release immediately
    phase HOLD — hold the button down for several seconds

Same strobe length in both => a fixed, self-timed window (a real data-ready line).
Longer in HOLD    => the strobe just tracks the button, and pin 1 is far less interesting.

WIRING: unchanged. Pull-ups on pins 1/2/3, nothing driven (the AWG is switched off in software).
Mic AWAKE, battery IN.

    python strobe_end_capture.py
    python strobe_end_capture.py --reps 3 --start-ms 100 --max-ms 2000
"""
import argparse
import datetime
import os
import time

from scpi_lib import Scope, Awg
from psu_lib import PSU
from clock_injection import PIN_CHANS, OUTDIR

FINDINGS = "findings"
DIVISIONS = 10          # DHO814 horizontal divisions


def scale(pre, raw):
    p = pre.split(",")
    xinc = float(p[4])
    yinc, yorig, yref = float(p[7]), float(p[8]), float(p[9])
    return xinc, [(b - yorig - yref) * yinc for b in raw]


def find_pulse(vals, hi_thresh=2.0, lo_thresh=1.0):
    """Locate the first high->low edge and the following low->high edge.

    Returns (fall_idx, rise_idx). rise_idx is None if the signal never comes back up —
    i.e. the strobe outlasted the record and the window must be widened.
    """
    fall = rise = None
    state = 1 if vals and vals[0] > hi_thresh else 0
    for i, v in enumerate(vals):
        if state == 1 and v < lo_thresh:
            state = 0
            if fall is None:
                fall = i
        elif state == 0 and v > hi_thresh:
            state = 1
            if fall is not None:
                rise = i
                break
    return fall, rise


def capture_one(scope, args, window_s, label):
    """Arm with the trigger at the far left, wait for a press, return a result dict."""
    tb = window_s / DIVISIONS
    # Positive offset moves the trigger LEFT; ~5 divisions puts it at the screen edge so the
    # record is almost entirely post-trigger.
    scope.arm_single(trig_ch=PIN_CHANS[1], level=args.thresh, slope="NEGative",
                     mdepth=10_000, tb_scale=tb, sweep="NORMal",
                     offset=tb * args.offset_div)
    print(f"    [{label}] window {window_s*1e3:.0f} ms — press the button "
          f"(up to {args.window:.0f}s)...", flush=True)
    if scope.wait_stop(timeout=args.window) != "STOP":
        return None
    time.sleep(0.5)
    pre, raw = scope.read_screen(PIN_CHANS[1])
    xinc, v = scale(pre, raw)
    fall, rise = find_pulse(v)
    return {"xinc": xinc, "n": len(v), "window_s": window_s, "fall": fall, "rise": rise,
            "pre": pre, "raw": raw,
            "dur_s": (rise - fall) * xinc if (fall is not None and rise is not None) else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2, help="captures per phase")
    ap.add_argument("--start-ms", type=float, default=100.0, help="initial window (ms)")
    ap.add_argument("--max-ms", type=float, default=2000.0, help="widen up to this (ms)")
    ap.add_argument("--offset-div", type=float, default=4.6,
                    help="divisions to shift the trigger left (10-div screen; ~4.6 keeps the "
                         "pre-trigger edge just visible)")
    ap.add_argument("--window", type=float, default=25.0, help="seconds to wait per press")
    ap.add_argument("--thresh", type=float, default=1.5)
    ap.add_argument("--rail", type=float, default=3.0)
    ap.add_argument("--ilim", type=float, default=0.02)
    ap.add_argument("--ovp", type=float, default=3.6)
    args = ap.parse_args()

    psu = PSU()
    awg = Awg(); print("AWG  :", awg.query("*IDN?"))
    scope = Scope(); print("SCOPE:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.8, offset=-2.0, coupling="DC")

    results = {"TAP": [], "HOLD": []}
    try:
        psu.bring_up(args.rail, args.ilim, ovp=args.ovp)
        awg.output(False, ch=1); awg.output(False, ch=2)   # nothing driven
        time.sleep(0.5)
        os.makedirs(OUTDIR, exist_ok=True); os.makedirs(FINDINGS, exist_ok=True)

        for phase, how in (("TAP", "PRESS AND RELEASE IMMEDIATELY"),
                           ("HOLD", "PRESS AND HOLD DOWN for ~5 seconds")):
            print(f"\n=== phase {phase}: {how} ===")
            for rep in range(1, args.reps + 1):
                window = args.start_ms / 1e3
                while True:
                    r = capture_one(scope, args, window, f"{phase} {rep}/{args.reps}")
                    if r is None:
                        print("      no trigger.")
                        break
                    if r["fall"] is None:
                        print("      triggered but no falling edge in the record — odd; skipping.")
                        break
                    if r["rise"] is not None:
                        print(f"      *** strobe ENDED: {r['dur_s']*1e3:.2f} ms "
                              f"(fall@{r['fall']}, rise@{r['rise']} of {r['n']}) ***")
                        tag = f"strobe_{phase}{rep}"
                        with open(f"{OUTDIR}/{tag}_ch1.bin", "wb") as f: f.write(r["raw"])
                        with open(f"{OUTDIR}/{tag}_ch1.pre", "w") as f: f.write(r["pre"])
                        results[phase].append(r["dur_s"])
                        break
                    # still low at the end of the record -> widen and retry
                    if window * 1e3 >= args.max_ms:
                        print(f"      still LOW at {window*1e3:.0f} ms (the ceiling). The strobe "
                              f"is longer than that.")
                        results[phase].append(None)
                        break
                    window *= 2
                    print(f"      still low at the end of the record — widening to "
                          f"{window*1e3:.0f} ms")
    finally:
        try:
            awg.output(False, ch=1); awg.output(False, ch=2)
        except Exception:
            pass
        psu.off(); awg.close(); scope.close()
        print("\nAWG + PSU OFF.")

    print("\n==== RESULTS ====")
    for phase in ("TAP", "HOLD"):
        vals = [v for v in results[phase] if v is not None]
        shown = ", ".join(f"{v*1e3:.2f} ms" for v in vals) if vals else "none measured"
        print(f"  {phase:4}: {shown}")

    tap = [v for v in results["TAP"] if v is not None]
    hold = [v for v in results["HOLD"] if v is not None]
    print("\n==== VERDICT ====")
    if not tap and not hold:
        print("  Nothing measured — the strobe outlasted every window, or no trigger. Re-run with")
        print("  a larger --max-ms.")
        return
    if tap and hold:
        mt, mh = sum(tap) / len(tap), sum(hold) / len(hold)
        print(f"  mean TAP {mt*1e3:.2f} ms   mean HOLD {mh*1e3:.2f} ms")
        if mh > mt * 1.5:
            print("  => the strobe TRACKS THE BUTTON: it stays low while the button is held.")
            print("     pin 1 is then closer to a button-contact mirror than a timed data-ready")
            print("     window, and a gated clock burst can be issued any time during the hold.")
        else:
            print("  => the strobe is a FIXED, SELF-TIMED window, independent of how long the")
            print("     button is held. That is exactly what a data-ready / request-to-send line")
            print("     looks like, and it gives a hard deadline for the gated burst: the clock")
            print(f"     must be delivered within ~{mt*1e3:.0f} ms of the falling edge.")
    else:
        print("  Only one phase produced a measurement — re-run before drawing a conclusion.")

    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = f"{FINDINGS}/strobe_end_{stamp}.txt"
    with open(path, "w") as f:
        f.write(f"pin-1 strobe end-to-end, trigger at far left, nothing driven\n{stamp}\n\n")
        for phase in ("TAP", "HOLD"):
            for i, v in enumerate(results[phase], 1):
                f.write(f"{phase} {i}: {'%.3f ms' % (v*1e3) if v is not None else 'not ended in window'}\n")
    print(f"\nsaved -> {path}")


if __name__ == "__main__":
    main()
