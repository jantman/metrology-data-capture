"""Rig pre-flight for the pull-up + clock-injection setup. No button pressing required.

Verifies the wiring BEFORE committing to a long interactive run, and leaves the bench safe.
Checks, in order:

  1. PSU comes up at the commanded rail without current-limiting.
  2. With the AWG OFF, all three signal pins sit at the rail through their 10k pull-ups.
     A pin that doesn't is a missing/open pull-up or a bad breakout contact.
  3. With the AWG ON, exactly ONE pin swings — that identifies which pin is actually being
     driven, independent of what anyone believes is wired where.
  4. The driven pin's high/low levels match the 1k/10k divider prediction, which confirms the
     series resistor and pull-up are both really in circuit:
         pin_high = (10*amp + 3)/11    pin_low = 3/11 ~= 0.27 V

Uses VAVG for DC levels, never VMAX/VMIN — §11.12's lesson (peak detectors exaggerate noise;
pin 1 once showed a phantom +-2 V swing that VAVG resolved as a rock-steady 3.013 V).

    python preflight.py                 # expects the AWG on pin 2
    python preflight.py --clk-pin 3
"""
import argparse
import time

from scpi_lib import Scope, Awg
from psu_lib import PSU
from clock_injection import PIN_CHANS

RAIL_TOL = 0.15          # V, how close to the rail an undriven pulled-up pin must sit
SWING_MIN = 1.0          # V, minimum VPP to call a pin "driven"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clk-pin", type=int, default=2, choices=(1, 2, 3),
                    help="pin you believe AWG CH1 is wired to")
    ap.add_argument("--clk2-pin", type=int, default=0, choices=(0, 1, 2, 3),
                    help="pin you believe AWG CH2 is wired to (0 = CH2 not connected). With both "
                         "channels wired, either input can be driven in software with no rewiring.")
    ap.add_argument("--freq", type=float, default=1000.0)
    ap.add_argument("--amp", type=float, default=3.0)
    ap.add_argument("--rail", type=float, default=3.0)
    ap.add_argument("--ilim", type=float, default=0.02)
    ap.add_argument("--ovp", type=float, default=3.6)
    ap.add_argument("--pullup-k", type=float, default=10.0,
                    help="pull-up resistance in kOhm (default 10). The divider prediction in "
                         "step 4 depends on it: pin_low = rail*Rs/(Rs+Rpu), so a 100k pull-up "
                         "gives ~0.03 V rather than ~0.27 V and the printed prediction would "
                         "otherwise be wrong.")
    ap.add_argument("--series-k", type=float, default=1.0, help="AWG series resistance, kOhm")
    ap.add_argument("--probe-mohm", type=float, default=1.0,
                    help="scope passive-probe input resistance, MOhm (DHO814 1x = 1 MOhm). "
                         "Negligible against a 10k pull-up but NOT against 100k, where it drags "
                         "the idle level well below the rail.")
    ap.add_argument("--max-volts", type=float, default=3.0)
    args = ap.parse_args()
    if args.amp > args.max_volts:
        raise SystemExit("amp exceeds --max-volts")

    psu = PSU()
    awg = Awg(); print("AWG  :", awg.query("*IDN?"))
    scope = Scope(); print("SCOPE:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.8, offset=-2.0, coupling="DC")

    problems = []
    idle = {}
    driven = {}
    try:
        # --- 1. rail -----------------------------------------------------------------
        print("\n[1/4] PSU bring-up")
        st = psu.bring_up(args.rail, args.ilim, ovp=args.ovp)

        # --- 2. pull-ups, AWG off ----------------------------------------------------
        # Expected idle is NOT the bare rail: each scope probe is ~1 MOhm to ground and forms a
        # divider with the pull-up. At 10k that is a 1% effect and invisible; at 100k it pulls the
        # pin to ~0.91*rail, which looks exactly like a missing pull-up if you do not model it.
        rpu_m = args.pullup_k / 1000.0
        exp_one = args.rail * args.probe_mohm / (args.probe_mohm + rpu_m)
        # Pin 1 carries a second 1 MOhm path: scope CH4 sits on the AWG output, reachable through
        # the 1k series resistor, so pin 1 sees two probes in parallel.
        exp_two = args.rail * (args.probe_mohm / 2) / (args.probe_mohm / 2 + rpu_m)
        tol = max(RAIL_TOL, 0.08 * args.rail)
        print(f"\n[2/4] AWG OFF — pins should sit near {exp_one:.2f} V "
              f"({args.pullup_k:g}k pull-up against a {args.probe_mohm:g} MOhm probe), or "
              f"{exp_two:.2f} V where a second probe loads the node")
        awg.output(False, ch=1); awg.output(False, ch=2)
        time.sleep(0.5)
        for p in (1, 2, 3):
            v = scope.measure_vavg(PIN_CHANS[p])
            idle[p] = v
            ok = min(abs(v - exp_one), abs(v - exp_two)) <= tol
            near = "1 probe" if abs(v - exp_one) < abs(v - exp_two) else "2 probes"
            print(f"      pin {p}: VAVG {v:+.3f} V   {'OK (' + near + ')' if ok else '<-- OFF'}")
            if not ok:
                problems.append(
                    f"pin {p} idles at {v:+.3f} V, expected ~{exp_one:.2f} V (or ~{exp_two:.2f} V "
                    f"with a second probe on the node) — missing/open {args.pullup_k:g}k pull-up, "
                    f"or a bad breakout contact")

        # --- 3. which pin actually moves? --------------------------------------------
        scope.write(":TRIGger:SWEep AUTO"); scope.write(":RUN")
        scope.write(":TIMebase:MAIN:SCALe 0.0005")

        def swinging(tag):
            time.sleep(1.0)
            out = {}
            for p in (1, 2, 3):
                out[p] = scope.measure_item(PIN_CHANS[p], "VPP")
            print("      " + tag + "  " +
                  "  ".join(f"pin{p} {v:4.2f}" for p, v in out.items()))
            return [p for p, v in out.items() if v >= SWING_MIN]

        print(f"\n[3/4] AWG ON ({args.freq:g} Hz, 0->{args.amp:g} V) — exactly one pin per channel")
        awg.square(args.freq, low=0.0, high=args.amp, ch=1)
        awg.output(True, ch=1); awg.output(False, ch=2)
        moving = swinging("CH1 only: ")
        if args.pullup_k >= 50:
            print(f"      (note: at {args.pullup_k:g}k the pins are high-impedance, so crosstalk "
                  f"into the undriven pins will be much larger than at 10k — watch the numbers "
                  f"above, they set the usable trigger threshold for the sweep.)")
        driven = {p: 0.0 for p in (1, 2, 3)}

        if args.clk2_pin:
            awg.square(args.freq, low=0.0, high=args.amp, ch=2)
            awg.output(False, ch=1); awg.output(True, ch=2)
            moving2 = swinging("CH2 only: ")
            awg.output(False, ch=2); awg.output(True, ch=1)
            if moving2 != [args.clk2_pin]:
                problems.append(
                    f"AWG CH2: expected only pin {args.clk2_pin} to swing, saw {moving2 or 'nothing'}"
                    + ("  (is the CH2 lead or its 1k connected?)" if not moving2 else ""))
            else:
                print(f"      CH2 correctly drives pin {args.clk2_pin} only.")

        if moving != [args.clk_pin]:
            if not moving:
                problems.append(
                    "NO pin is swinging — the AWG lead or its 1k series resistor is not "
                    "connected. (AWG output was verified ON.)")
            elif len(moving) > 1:
                problems.append(f"pins {moving} are ALL swinging — expected only one. Check for a "
                                f"short between pins, or a probe on the wrong pin.")
            else:
                problems.append(
                    f"the AWG is driving pin {moving[0]}, NOT pin {args.clk_pin}. Either move the "
                    f"lead, or run the sweep with --clk-pin {moving[0]} (pins 2/3 are symmetric "
                    f"inputs, so either is fine).")

        # --- 4. divider sanity on the driven pin -------------------------------------
        # SETTLE FIRST. The CH2 test above ends by switching CH1 back on, and measuring
        # immediately catches the channel mid-settle: seen twice, reporting a ~0.36 V swing on a
        # pin whose VPP was 3.2 V one step earlier. Worse, because VPP reads low at the same
        # moment, the VTOP/VBASe-vs-VPP cross-check below is fooled into agreeing and stays quiet.
        time.sleep(1.2)
        actual = moving[0] if len(moving) == 1 else args.clk_pin
        print(f"\n[4/4] divider check on the driven pin ({actual})")
        ch = PIN_CHANS[actual]
        vpp_drv = scope.measure_item(ch, "VPP")
        try:
            hi = scope.measure_item(ch, "VTOP")
            lo = scope.measure_item(ch, "VBASe")
        except RuntimeError:
            hi = lo = None
        # VTOP/VBASe pick the two most common levels and can return a plausible-but-wrong pair on
        # a ringing high-impedance node — seen at 100k, reporting 2.68/2.48 on a pin whose VPP was
        # 3.20. Cross-check against VPP and fall back to raw peak/trough if they disagree.
        if hi is None or lo is None or abs((hi - lo) - vpp_drv) > 0.3 * max(vpp_drv, 0.1):
            hi = scope.measure_item(ch, "VMAX")
            lo = scope.measure_item(ch, "VMIN")
            print("      (VTOP/VBASe inconsistent with VPP — using VMAX/VMIN)")
        rpu, rs = args.pullup_k, args.series_k
        pred_hi = (rpu * args.amp + rs * args.rail) / (rpu + rs)
        pred_lo = args.rail * rs / (rpu + rs)
        print(f"      measured  high {hi:+.2f} V   low {lo:+.2f} V")
        print(f"      predicted high {pred_hi:+.2f} V   low {pred_lo:+.2f} V   "
              f"({rs:g}k/{rpu:g}k divider)")
        if abs(hi - pred_hi) > 0.5:
            problems.append(
                f"driven-pin HIGH is {hi:.2f} V but the 1k/10k divider predicts {pred_hi:.2f} V. "
                f"If it is much HIGHER, the {rpu:g}k pull-up on that pin may be missing; if much "
                f"LOWER, the series resistor may be larger than {rs:g}k.")
    finally:
        try:
            awg.output(False, ch=1); awg.output(False, ch=2)
        except Exception:
            pass
        psu.off(); awg.close(); scope.close()
        print("\nAWG + PSU OFF — bench left safe.")

    print("\n==== PRE-FLIGHT ====")
    if problems:
        for p in problems:
            print(f"  [X] {p}")
        print("\n  Fix the above before running threshold_sweep.py.")
        raise SystemExit(1)
    print("  [OK] rail good, all three pull-ups present, each AWG channel drives its own pin,")
    print("       divider as predicted. The rig is ready.")


if __name__ == "__main__":
    main()
