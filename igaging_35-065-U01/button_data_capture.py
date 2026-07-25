"""Test whether the on-device DATA button gates/enables the data output.

Earlier DATA-button tests ran under the 1 ohm-load over-voltage bug and a fragile capture, so
they're void. This redo uses correct tooling: VDD on pin 1, a continuous 3 V clock on pin 2
(host-clocked -> DATA only appears while clocked), and the scope armed to TRIGGER THE MOMENT
pin 3 rises past the crosstalk ceiling. Crosstalk peaks at ~+0.4 V, so a trigger at +1.0 V
cannot fire on coupling — only a genuinely driven (rail-clamped) DATA line trips it. You mash
the DATA button during the arm window; a trigger = real data, a timeout = clean negative.

    python button_data_capture.py                 # VDD=3, clock pin2, watch pin3
    python button_data_capture.py --thresh 0.8 --secs 45

Wiring unchanged: CH1->1k->pin2 (clock), CH2->870R->pin1 (VDD), 10k pull-down pin3, scope
CH1..3 on pins 1..3, CH4 on AWG CH1 out, grounds pin 4.
"""
import argparse
import os
import time

from scpi_lib import Scope, Awg
from clock_injection import digitize_transitions, PIN_CHANS, OUTDIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clk-pin", type=int, default=2, choices=(1, 2, 3))
    ap.add_argument("--data-pin", type=int, default=3, choices=(1, 2, 3))
    ap.add_argument("--vdd", type=float, default=3.0)
    ap.add_argument("--amp", type=float, default=3.0)
    ap.add_argument("--freq", type=float, default=9000)
    ap.add_argument("--thresh", type=float, default=1.0, help="pin3 trigger level (V), above crosstalk")
    ap.add_argument("--secs", type=float, default=40.0, help="button-press window (s)")
    ap.add_argument("--max-volts", type=float, default=3.0)
    args = ap.parse_args()
    if args.vdd > args.max_volts or args.amp > args.max_volts:
        raise SystemExit("vdd/amp exceeds --max-volts; refusing")

    drive_ch = PIN_CHANS[args.clk_pin]
    data_ch = PIN_CHANS[args.data_pin]
    awg = Awg(); print("AWG IDN:", awg.query("*IDN?"))
    scope = Scope(); print("SCOPE IDN:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.8, offset=-2.0, coupling="DC")

    try:
        # VDD on pin 1, continuous clock on the clk pin
        awg.dc(args.vdd, ch=2); awg.output(True, ch=2)
        awg.square(args.freq, low=0.0, high=args.amp, ch=1); awg.output(True, ch=1)
        time.sleep(0.4)

        # Sanity: confirm crosstalk baseline on pin3 is below the trigger threshold
        scope.write(":TRIGger:SWEep AUTO"); scope.write(":RUN")
        scope.write(":TIMebase:MAIN:SCALe 0.0004")
        time.sleep(0.8)
        base_top = scope.measure_item(data_ch, "VTOP")
        print(f"\npin{args.data_pin} crosstalk VTOP ~{base_top:.2f} V; trigger set at "
              f"{args.thresh:.2f} V (must be well above baseline to avoid false trips).")

        # Arm: trigger the instant pin3 rises past the threshold (NORMal -> only stops on a
        # real edge above crosstalk). Window shows a frame's worth around the trigger.
        scope.arm_single(trig_ch=data_ch, level=args.thresh, slope="POSitive",
                         mdepth=1_000_000, tb_scale=0.0004, sweep="NORMal")
        print("\n" + "=" * 64)
        print(f"  >>> PRESS / HOLD / TAP the DATA button REPEATEDLY for ~{args.secs:.0f}s NOW <<<")
        print(f"      (clock is running on pin {args.clk_pin}; watching pin {args.data_pin})")
        print("=" * 64)
        status = scope.wait_stop(timeout=args.secs)

        if status == "STOP":
            os.makedirs(OUTDIR, exist_ok=True)
            tag = "button_data"
            vals = {}
            for ch in (1, 2, 3, 4):
                pre, raw = scope.read_raw(ch)
                with open(f"{OUTDIR}/{tag}_ch{ch}.bin", "wb") as f: f.write(raw)
                with open(f"{OUTDIR}/{tag}_ch{ch}.pre", "w") as f: f.write(pre)
                vals[ch] = digitize_transitions(pre, raw)
            scope.screenshot(f"{OUTDIR}/{tag}_scope.png")
    finally:
        awg.output(False, ch=1); awg.output(False, ch=2)
        awg.close(); scope.close()
        print("AWG CH1+CH2 OFF.")

    print("\n==== RESULT ====")
    if status == "STOP":
        dt, dv = vals[data_ch]
        print(f"*** TRIGGERED — pin{args.data_pin} rose above {args.thresh} V while pressing DATA! "
              f"({dt} transitions, vpp={dv:.2f} V) ***")
        print(f"That's above the crosstalk ceiling -> the button likely GATES the data output.")
        print(f"Analyze: python analyze_capture.py {OUTDIR}/button_data "
              f"--clk-pin {args.clk_pin} --data-pin {args.data_pin}")
    else:
        print(f"No trigger in {args.secs:.0f}s (status {status}). pin{args.data_pin} never rose "
              f"above {args.thresh} V — the DATA button did NOT enable a driven output while "
              f"clocking pin {args.clk_pin}. (Next: try clock OFF for a self-clocked frame, or a "
              f"different clk/data pairing.)")


if __name__ == "__main__":
    main()
