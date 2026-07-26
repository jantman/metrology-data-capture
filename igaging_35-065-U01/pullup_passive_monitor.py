"""TEST 1 — passive open-collector probe: pull all 3 signal pins UP to +3 V, watch for a dip.

The board's data outputs are open-collector (MMBT3904 NPN + 330k base, see §11.11 / board photos):
they can only pull LOW and float otherwise, so every prior test — which used a pull-DOWN or no
pull-up — was blind to them. Here the bench supply holds a +3 V rail and each signal pin is
pulled up to it; if the mic drives ANY pin (self-clocked clock/data on button press or motion),
that pin snaps 3 V -> ~0 and we catch it. Nothing is injected.

Wiring (see the test tables): PSU +3 V (I-limit ~20 mA) -> 10k -> each of pins 1/2/3;
PSU - and all scope grounds -> pin 4; scope CH1/2/3 on pins 1/2/3; AWG unused.

    python pullup_passive_monitor.py                 # monitor all 3 pins ~40 s
    python pullup_passive_monitor.py --capture-pin 3 # arm a falling-edge capture on pin 3

Procedure: run it, then PRESS THE DATA BUTTON repeatedly and slowly TURN THE SPINDLE for the
whole window. A pin whose VMIN drops well below the 3 V rail is an active (open-collector) line.
"""
import argparse
import os
import time

from scpi_lib import Scope
from psu_lib import PSU
from clock_injection import digitize_transitions, PIN_CHANS, OUTDIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--secs", type=float, default=40.0)
    ap.add_argument("--rail", type=float, default=3.0, help="pull-up rail voltage (V)")
    ap.add_argument("--ilim", type=float, default=0.02, help="PSU current limit (A)")
    ap.add_argument("--ovp", type=float, default=3.6)
    ap.add_argument("--thresh", type=float, default=1.5,
                    help="a pin dipping below this V (from the ~3 V rail) = active/driven")
    ap.add_argument("--capture-pin", type=int, default=0, choices=(0, 1, 2, 3),
                    help="instead of monitoring, arm a falling-edge capture on this pin")
    args = ap.parse_args()

    psu = PSU()
    scope = Scope(); print("SCOPE:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.8, offset=-2.0, coupling="DC")

    try:
        psu.bring_up(args.rail, args.ilim, ovp=args.ovp)

        if args.capture_pin:
            # Falling-edge triggered capture: catch a real frame at high resolution.
            ch = PIN_CHANS[args.capture_pin]
            print(f"\n>>> Armed on pin {args.capture_pin} (falling through {args.thresh} V). "
                  f"PRESS DATA / MOVE SPINDLE for ~{args.secs:.0f}s. <<<")
            scope.arm_single(trig_ch=ch, level=args.thresh, slope="NEGative",
                             mdepth=1_000_000, tb_scale=0.0004, sweep="NORMal")
            status = scope.wait_stop(timeout=args.secs)
            if status == "STOP":
                os.makedirs(OUTDIR, exist_ok=True)
                tag = f"pullup_frame_p{args.capture_pin}"
                for c in (1, 2, 3, 4):
                    pre, raw = scope.read_raw(c)
                    with open(f"{OUTDIR}/{tag}_ch{c}.bin", "wb") as f: f.write(raw)
                    with open(f"{OUTDIR}/{tag}_ch{c}.pre", "w") as f: f.write(pre)
                    t, v = digitize_transitions(pre, raw)
                    print(f"  pin{c if c in (1,2,3) else 'AWG'} ch{c}: {t} transitions, vpp={v:.2f}")
                scope.screenshot(f"{OUTDIR}/{tag}_scope.png")
                print(f"\n*** CAPTURED a falling edge on pin {args.capture_pin} — real frame! "
                      f"Analyze: python analyze_capture.py {OUTDIR}/{tag} "
                      f"--data-pin {args.capture_pin} ***")
            else:
                print(f"\nNo falling edge on pin {args.capture_pin} in {args.secs:.0f}s "
                      f"(status {status}).")
            return

        # Monitor mode: track the minimum each pin reaches.
        scope.write(":TRIGger:SWEep AUTO"); scope.write(":RUN")
        scope.write(":TIMebase:MAIN:SCALe 0.001")  # 10 ms window
        time.sleep(0.8)
        print(f"\n>>> PRESS DATA repeatedly and TURN THE SPINDLE for ~{args.secs:.0f}s NOW <<<\n")
        floor = {1: 9.0, 2: 9.0, 3: 9.0}
        hits = {1: 0, 2: 0, 3: 0}
        n = 0
        t0 = time.time()
        while time.time() - t0 < args.secs:
            row = {}
            flagged = False
            for p in (1, 2, 3):
                vmin = scope.measure_item(PIN_CHANS[p], "VMIN")
                floor[p] = min(floor[p], vmin)
                row[p] = vmin
                if vmin < args.thresh:
                    hits[p] += 1; flagged = True
            n += 1
            if flagged or n % 10 == 0:
                print(f"  t={time.time()-t0:5.1f}s  " +
                      " ".join(f"p{p} VMIN={row[p]:+.2f}" for p in (1, 2, 3)) +
                      ("   <== DIP!" if flagged else ""))
        scope.screenshot(f"{OUTDIR}/pullup_passive_scope.png") if os.path.isdir(OUTDIR) else None

        print("\n==== RESULT ====")
        for p in (1, 2, 3):
            print(f"  pin{p}: lowest VMIN {floor[p]:+.2f} V, {hits[p]}/{n} samples below "
                  f"{args.thresh} V")
        active = [p for p in (1, 2, 3) if floor[p] < args.thresh]
        if active:
            print(f"\n*** Pin(s) {active} pulled LOW off the 3 V rail -> ACTIVE open-collector "
                  f"line(s)! The mic IS driving them. ***")
            print(f"Next: capture the frame -> python pullup_passive_monitor.py "
                  f"--capture-pin {active[0]}")
        else:
            print("\nAll pins stayed at the 3 V rail -> no self-clocked OC output on button/motion. "
                  "Next: TEST 2 (inject clock + pull-up on DATA) via pullup_clock_capture.py.")
    finally:
        psu.off(); scope.close()
        print("PSU output OFF.")


if __name__ == "__main__":
    main()
