"""Is pin 1 an MCU output, or just the DATA button's contact wired to the connector?

WHY. §11.18 showed the button alone drives pin 1 low; strobe_end_capture then showed the low
lasts ~155 ms on a tap and **>3.2 s while held** — it tracks the button rather than being a fixed
self-timed window. A switch contact brought out to the connector would explain every observation
at once: the ~0 V low (§11.18), the reading-independence (§11.16), the fact that nothing ever
shifts out of it, and why driving pin 1 does nothing (§11.15 — you would just be fighting a closed
switch).

THE DISCRIMINATOR. **With the BATTERY OUT, a mechanical switch still conducts. A transistor
cannot.** §11.17b already supplies the button-released half (OL, battery out); this adds the held
half.

    battery out + button held + pin 1 conducts to GND  => mechanical switch contact
    battery out + button held + pin 1 stays open       => MCU-driven output, needs power

TWO METHOD FIXES over the first attempt, which produced a bogus "switch" verdict:

  * CONTINUITY mode, not resistance. The first run used auto-ranging resistance, where the meter
    emits transient near-zero readings while hunting for a range — it reported 0.0 ohms with the
    probes on an OPEN circuit, which is not physical. Continuity mode is fixed-range.
  * MEDIAN and sustained runs, never the minimum. Taking min-of-samples let a single transient
    decide the verdict — the same extremum-statistic trap as the VMIN peak detector that produced
    three false negatives in this project (review.md §1.3, §2.2). A closed contact is present for
    essentially the whole hold window, so it must show up in the median.

  * And a POSITIVE CONTROL: short pin 1 to pin 4 with a jumper first. If the method cannot see a
    deliberate short, nothing it says about the button means anything.

*** BATTERY OUT. *** Breakout connected, DMM leads on pin 1 and pin 4 (polarity irrelevant).

    python button_switch_test.py

Everything is teed to findings/button_switch_latest.txt, flushed per line.
"""
import argparse
import datetime
import os
import shutil
import statistics
import time

from dmm_lib import DMM

FINDINGS = "findings"
LOG_PATH = os.path.join(FINDINGS, "button_switch_latest.txt")
CLOSED_MAX = 100.0        # ohms; a closed contact reads well under this
OPEN_MIN = 1e5            # ohms; above this the path is open for our purposes


def is_num(v):
    """A real reading rather than the meter's ~1e9 overload sentinel."""
    return isinstance(v, float) and abs(v) < OPEN_MIN

_log_fh = None


def log(msg=""):
    print(msg)
    if _log_fh:
        _log_fh.write(msg + "\n")
        _log_fh.flush()
        os.fsync(_log_fh.fileno())


def ask(prompt):
    try:
        ans = input(prompt)
    except EOFError:
        log(prompt + "  [EOF — no TTY]")
        raise SystemExit("\nNeeds a real terminal: cd igaging_35-065-U01 && python "
                         "button_switch_test.py")
    if _log_fh:
        _log_fh.write(f"{prompt}{ans}\n"); _log_fh.flush()
    return ans


def sample(d, secs, func):
    """Poll for `secs`; return a dict of robust statistics (never a bare min)."""
    vals = []
    t0 = time.time()
    while time.time() - t0 < secs:
        try:
            vals.append(d.measurement()["value"])
        except Exception:
            pass
        time.sleep(0.12)
    if not vals:
        return None
    closed = [v for v in vals if abs(v) < CLOSED_MAX]
    longest = cur = 0
    for v in vals:
        cur = cur + 1 if abs(v) < CLOSED_MAX else 0
        longest = max(longest, cur)
    return {"n": len(vals), "median": statistics.median(vals), "min": min(vals),
            "frac_closed": len(closed) / len(vals), "longest_closed": longest}


def show(tag, s):
    if not s:
        log(f"    {tag}: no readings")
        return
    med = "OL/open" if abs(s["median"]) > OPEN_MIN else f"{s['median']:,.1f} Ω"
    log(f"    {tag}: median {med}  <-- the verdict rests on this and the consecutive run")
    log(f"        closed-samples {s['frac_closed']*100:.0f}% ({s['longest_closed']} consecutive)"
        f"   [%-of-window is reaction time, not physics; min {s['min']:,.1f} is transient-prone]")


def main():
    global _log_fh
    ap = argparse.ArgumentParser()
    ap.add_argument("--secs", type=float, default=8.0, help="sampling window per step")
    ap.add_argument("--pin", type=int, default=1, choices=(1, 2, 3))
    ap.add_argument("--mode", choices=("continuity", "resistance"), default="continuity")
    ap.add_argument("--skip-control", action="store_true")
    args = ap.parse_args()

    os.makedirs(FINDINGS, exist_ok=True)
    _log_fh = open(LOG_PATH, "w")
    func = "CONTINUITY" if args.mode == "continuity" else "RESISTANCE"

    try:
        log("=" * 72)
        log(f"pin {args.pin} vs GND, BATTERY OUT — is pin {args.pin} a switch contact?")
        log(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}   mode={func}")
        log("=" * 72)
        d = DMM()
        log(f"DMM: {d.identify()}")
        log(f"\n*** BATTERY OUT. DMM leads on pin {args.pin} and pin 4 (GND). ***")
        ask("    press Enter when ready: ")
        d.set_function(func)
        log(f"meter in {func} mode ({d.state()})\n")

        ctrl = None
        if not args.skip_control:
            log("[control] POSITIVE CONTROL — the method must be able to see a real short.")
            log(f"          Jumper pin {args.pin} directly to pin 4 (leave the DMM leads on).")
            ask("          jumper fitted? press Enter: ")
            ctrl = sample(d, args.secs, func)
            show("control (shorted)", ctrl)
            if not ctrl or ctrl["frac_closed"] < 0.8:
                log("\n  *** CONTROL FAILED — a deliberate short did not read as closed. The")
                log("  measurement method is not working (leads, mode, or contact). Everything")
                log("  else would be meaningless, so stopping here. ***")
                return
            log("          control OK — the method can see a closed contact.\n")
            ask(f"          REMOVE the jumper, then press Enter: ")

        log(f"[1/2] Button RELEASED — don't touch the mic. Sampling {args.secs:.0f}s...")
        rel = sample(d, args.secs, func)
        show("released", rel)

        log(f"\n[2/2] *** PRESS AND HOLD THE DATA BUTTON *** for the next {args.secs:.0f}s...")
        time.sleep(1.0)
        hel = sample(d, args.secs, func)
        show("held", hel)
        log("      (you can let go)")

        log("\n==== VERDICT ====")
        if not rel or not hel:
            log("  Missing readings — re-run.")
            return
        # Decide on the MEDIAN plus a sustained run — never on frac_closed alone.
        # frac_closed measures how much of the sampling window the button happened to be down
        # for, which is human reaction time, not physics. A 2026-07-26 run read median 0.8 Ohm
        # while held (identical to the jumpered control) with 23 consecutive closed samples, and
        # a >=0.7 fraction gate rejected it at 55% and printed "NOT a switch" — the exact
        # opposite of the truth. The median and the longest run are the physical signals.
        def closed(st):
            return (is_num(st["median"]) and abs(st["median"]) < CLOSED_MAX
                    and st["longest_closed"] >= 5)

        held_closed = closed(hel)
        rel_closed = closed(rel)
        if held_closed and not rel_closed:
            log(f"  *** MECHANICAL SWITCH CONTACT. *** pin {args.pin} conducts to ground while")
            log("  the button is held, with NO POWER APPLIED. A transistor cannot do that.")
            log("\n  Consequences: §11.15's \"pin 1 = the mic's sole OUTPUT\" is wrong in kind —")
            log("  the mic has NO output on the connector, so the measurement data must come out")
            log("  on pins 2/3. Explains the ~0 V low, the reading-independence (§11.16), and why")
            log("  driving pin 1 does nothing. Vindicates the review.md §10.5 lead.")
        elif held_closed and rel_closed:
            log("  Both states read CLOSED — the leads are shorted somewhere, or the jumper is")
            log("  still fitted. Re-check the rig and re-run.")
        else:
            log(f"  NOT a switch. pin {args.pin} stays OPEN while the button is held with no")
            log("  power, so the low seen in §11.18 requires the mic to be powered.")
            log("\n  => pin 1 IS an MCU-driven output that mirrors the button in firmware.")
            log("  §11.15's pin roles stand, and the ~155 ms / >3.2 s behaviour is deliberate.")
            log("  Since holding the button holds pin 1 low indefinitely, the gated-burst")
            log("  experiment has an unlimited window rather than a 155 ms deadline.")
    except KeyboardInterrupt:
        log("\n[interrupted — partial results above]")
    except Exception as e:
        log(f"\n[ERROR] {type(e).__name__}: {e}")
        raise
    finally:
        if _log_fh:
            _log_fh.write(f"\nfinished {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
            _log_fh.close(); _log_fh = None
        try:
            shutil.copyfile(LOG_PATH, os.path.join(
                FINDINGS, f"button_switch_{datetime.datetime.now():%Y-%m-%d_%H%M%S}.txt"))
        except OSError:
            pass
        print(f"\nlog -> {LOG_PATH}")


if __name__ == "__main__":
    main()
