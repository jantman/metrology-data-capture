"""Time-series of the three pins' idle levels — an awake/asleep detector, and a rig sanity check.

WHY. Nothing in the rig has ever been able to tell whether the mic is awake, so every sweep has
relied on the operator remembering (§11.21 records this as a systematic gap, and §11.7 records an
early run invalidated by exactly it). Auto-off is ~27 min, measured 2026-08-09.

At 10k pull-ups any state-dependent loading would be swamped — a 1 MOhm probe already only shifts
the level 1%. At **100k** the pins are high-impedance enough that a change in the mic's internal
input loading should move the idle level visibly. This samples all three continuously so the
transition appears as a step.

WHY NOT JUST READ THE PINS ONCE. A first attempt read each pin in turn with measure_vavg, ~8 s per
pin, ~25 s total. The mic changed state mid-read, so different pins were measured in different
states and the result was incoherent nonsense. This configures the scope ONCE and then polls, so a
full three-pin sample takes well under a second and a state change lands between samples rather
than inside one.

Run it, then change the mic's state partway through (wake it, or let it sleep, or power-cycle it)
and watch for a step.

    python mic_state_monitor.py --secs 90
    python mic_state_monitor.py --secs 60 --rail 3.0
"""
import argparse
import datetime
import os
import time

from scpi_lib import Scope, Awg
from psu_lib import PSU
from clock_injection import PIN_CHANS

FINDINGS = "findings"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secs", type=float, default=90.0)
    ap.add_argument("--rail", type=float, default=3.0)
    ap.add_argument("--ilim", type=float, default=0.02)
    ap.add_argument("--ovp", type=float, default=3.6)
    ap.add_argument("--step-mv", type=float, default=40.0,
                    help="a jump this large between consecutive samples is flagged as a step")
    args = ap.parse_args()

    os.makedirs(FINDINGS, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = f"{FINDINGS}/mic_state_{stamp}.txt"
    fh = open(path, "w")

    def log(m):
        print(m, flush=True)
        fh.write(m + "\n"); fh.flush()

    psu = PSU()
    awg = Awg()
    scope = Scope()
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.8, offset=-2.0, coupling="DC")

    rows = []
    try:
        psu.bring_up(args.rail, args.ilim, ovp=args.ovp)
        awg.output(False, ch=1); awg.output(False, ch=2)      # nothing driven
        # Configure the scope ONCE, then only query — this is what makes a sample fast.
        scope.write(":TRIGger:SWEep AUTO")
        scope.write(":RUN")
        scope.write(":TIMebase:MAIN:SCALe 0.001")
        time.sleep(1.0)

        log(f"idle-level monitor, rail {args.rail:g} V, nothing driven — {stamp}")
        log("CHANGE THE MIC'S STATE partway through (wake it / let it sleep) and watch for a step.")
        log("")
        log(f"{'t (s)':>7}  {'pin1':>8} {'pin2':>8} {'pin3':>8}")
        t0 = time.time()
        prev = None
        while time.time() - t0 < args.secs:
            t = time.time() - t0
            v = [scope.measure_item(PIN_CHANS[p], "VAVG") for p in (1, 2, 3)]
            mark = ""
            if prev and max(abs(a - b) for a, b in zip(v, prev)) > args.step_mv / 1000.0:
                mark = "   <== STEP"
            log(f"{t:7.1f}  {v[0]:8.4f} {v[1]:8.4f} {v[2]:8.4f}{mark}")
            rows.append((t, v))
            prev = v
    finally:
        psu.off(); awg.close(); scope.close()
        log("\nPSU OFF.")

    if len(rows) > 3:
        log("\n==== SUMMARY ====")
        for i, p in enumerate((1, 2, 3)):
            col = [r[1][i] for r in rows]
            log(f"  pin {p}: min {min(col):+.4f}  max {max(col):+.4f}  "
                f"spread {(max(col)-min(col))*1000:6.1f} mV")
        spread = max(max(r[1][i] for r in rows) - min(r[1][i] for r in rows) for i in range(3))
        log("")
        if spread * 1000 > args.step_mv:
            log(f"  A pin moved by {spread*1000:.0f} mV during the run. If that coincides with the")
            log("  state change, the idle level IS a usable awake/asleep detector — bake the")
            log("  measured threshold into preflight so every sweep verifies its own precondition.")
        else:
            log(f"  All pins stable to within {spread*1000:.0f} mV. Either the state did not change")
            log("  during the run, or idle level does not track it — in which case there is still")
            log("  no rig-side awake detector and the operator has to confirm the LCD.")
    fh.close()
    print(f"\nsaved -> {path}")


if __name__ == "__main__":
    main()
