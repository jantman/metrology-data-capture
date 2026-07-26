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
                    help="which pin you believe the AWG is wired to")
    ap.add_argument("--freq", type=float, default=1000.0)
    ap.add_argument("--amp", type=float, default=3.0)
    ap.add_argument("--rail", type=float, default=3.0)
    ap.add_argument("--ilim", type=float, default=0.02)
    ap.add_argument("--ovp", type=float, default=3.6)
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
        print(f"\n[2/4] AWG OFF — all three pins should sit at ~{args.rail:g} V via their 10k "
              f"pull-ups")
        awg.output(False, ch=1); awg.output(False, ch=2)
        time.sleep(0.5)
        for p in (1, 2, 3):
            v = scope.measure_vavg(PIN_CHANS[p])
            idle[p] = v
            ok = abs(v - args.rail) <= RAIL_TOL
            print(f"      pin {p}: VAVG {v:+.3f} V   {'OK' if ok else '<-- NOT AT RAIL'}")
            if not ok:
                problems.append(
                    f"pin {p} idles at {v:+.3f} V, not ~{args.rail:g} V — missing/open 10k "
                    f"pull-up, or a bad breakout contact on that pin")

        # --- 3. which pin actually moves? --------------------------------------------
        print(f"\n[3/4] AWG ON ({args.freq:g} Hz, 0->{args.amp:g} V) — exactly one pin should swing")
        awg.square(args.freq, low=0.0, high=args.amp, ch=1)
        awg.output(True, ch=1)
        scope.write(":TRIGger:SWEep AUTO"); scope.write(":RUN")
        scope.write(":TIMebase:MAIN:SCALe 0.0005")
        time.sleep(1.0)
        for p in (1, 2, 3):
            vpp = scope.measure_item(PIN_CHANS[p], "VPP")
            driven[p] = vpp
            print(f"      pin {p}: VPP {vpp:5.2f} V   {'<== DRIVEN' if vpp >= SWING_MIN else ''}")
        moving = [p for p, v in driven.items() if v >= SWING_MIN]
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
        actual = moving[0] if len(moving) == 1 else args.clk_pin
        print(f"\n[4/4] divider check on the driven pin ({actual})")
        ch = PIN_CHANS[actual]
        try:
            hi = scope.measure_item(ch, "VTOP")
        except RuntimeError:
            hi = scope.measure_item(ch, "VMAX")
        try:
            lo = scope.measure_item(ch, "VBASe")
        except RuntimeError:
            lo = scope.measure_item(ch, "VMIN")
        pred_hi = (10 * args.amp + args.rail) / 11
        pred_lo = args.rail / 11
        print(f"      measured  high {hi:+.2f} V   low {lo:+.2f} V")
        print(f"      predicted high {pred_hi:+.2f} V   low {pred_lo:+.2f} V   (1k/10k divider)")
        if abs(hi - pred_hi) > 0.5:
            problems.append(
                f"driven-pin HIGH is {hi:.2f} V but the 1k/10k divider predicts {pred_hi:.2f} V. "
                f"If it is much HIGHER, the 10k pull-up on that pin may be missing; if much "
                f"LOWER, the series resistor may be larger than 1k.")
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
    print("  [OK] rail good, all three pull-ups present, exactly one pin driven, divider as")
    print("       predicted. The rig is ready — run:")
    print(f"           python threshold_sweep.py --clk-pin {args.clk_pin}")


if __name__ == "__main__":
    main()
