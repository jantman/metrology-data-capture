"""TEST 2 — host-clocked open-collector read: inject a clock, pull DATA UP, watch it dip low.

If Test 1 (passive) is quiet, the mic may be host-clocked. Drive a clock into the CLK pin while
the DATA pin is pulled UP to +3 V (bench supply). An open-collector DATA output rests at the 3 V
rail and gets pulled toward 0 for each data bit — the opposite of our old pull-DOWN, which
masked it. A data-pin whose VMIN dips well below the rail (while VMAX stays ~3 V) is real data.

Wiring: AWG CH1 -> 1k -> CLK pin (--clk-pin); PSU +3 V -> 10k -> DATA pin (--data-pin) [and
optionally -> 10k -> pin 1]; PSU - and all grounds -> pin 4; scope CH1/2/3 on pins 1/2/3,
CH4 on AWG CH1 out.

    python pullup_clock_capture.py --clk-pin 2 --data-pin 3
    python pullup_clock_capture.py --clk-pin 2 --data-pin 3 --mode burst
"""
import argparse
import os
import time

from scpi_lib import Scope, Awg
from psu_lib import PSU
from clock_injection import PIN_CHANS, OUTDIR
from burst_capture import configure_burst

CLK_PRESENT_V = 1.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clk-pin", type=int, default=2, choices=(1, 2, 3))
    ap.add_argument("--data-pin", type=int, default=3, choices=(1, 2, 3))
    ap.add_argument("--freq", type=float, default=9000)
    ap.add_argument("--amp", type=float, default=3.0, help="clock HIGH level (V)")
    ap.add_argument("--mode", choices=("continuous", "burst"), default="continuous")
    ap.add_argument("--ncycles", type=int, default=21)
    ap.add_argument("--period-ms", type=float, default=10.0)
    ap.add_argument("--rail", type=float, default=3.0)
    ap.add_argument("--ilim", type=float, default=0.02)
    ap.add_argument("--ovp", type=float, default=3.6)
    ap.add_argument("--thresh", type=float, default=1.5,
                    help="DATA dipping below this (from ~3 V rail) = real driven bit")
    ap.add_argument("--max-volts", type=float, default=3.0)
    args = ap.parse_args()
    if args.amp > args.max_volts:
        raise SystemExit("amp exceeds --max-volts")

    clk_ch, data_ch = PIN_CHANS[args.clk_pin], PIN_CHANS[args.data_pin]
    psu = PSU()
    awg = Awg(); print("AWG:", awg.query("*IDN?"))
    scope = Scope(); print("SCOPE:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.8, offset=-2.0, coupling="DC")

    try:
        psu.bring_up(args.rail, args.ilim, ovp=args.ovp)

        if args.mode == "burst":
            configure_burst(awg, args.freq, args.amp, args.ncycles, args.period_ms / 1000.0)
            tag = f"pullup_clk_burst_p{args.clk_pin}"
        else:
            awg.square(args.freq, low=0.0, high=args.amp, ch=1)
            tag = f"pullup_clk_cont_p{args.clk_pin}"
        awg.output(True, ch=1)
        time.sleep(0.4)
        print(f"\n{args.mode} clock {args.freq:g} Hz, {args.amp:g} V on pin {args.clk_pin}; "
              f"DATA pin {args.data_pin} pulled to {args.rail:g} V.")

        win_ms = 4.0 if args.mode == "continuous" else args.period_ms * 2.5
        scope.write(":TRIGger:SWEep AUTO"); scope.write(":RUN")
        scope.write(f":TIMebase:MAIN:SCALe {win_ms / 1000.0 / 10.0}")
        time.sleep(1.0)
        vpp = {ch: scope.measure_item(ch, "VPP") for ch in (1, 2, 3)}
        vmin = {ch: scope.measure_item(ch, "VMIN") for ch in (1, 2, 3)}
        vmax = {ch: scope.measure_item(ch, "VMAX") for ch in (1, 2, 3)}
        os.makedirs(OUTDIR, exist_ok=True)
        for ch in (1, 2, 3, 4):
            pre, raw = scope.read_raw(ch)
            with open(f"{OUTDIR}/{tag}_ch{ch}.bin", "wb") as f: f.write(raw)
            with open(f"{OUTDIR}/{tag}_ch{ch}.pre", "w") as f: f.write(pre)
        scope.screenshot(f"{OUTDIR}/{tag}_scope.png")
    finally:
        try:
            awg.write(":SOURce1:BURSt:STATe OFF"); awg.output(False, ch=1)
        except Exception:
            pass
        psu.off(); awg.close(); scope.close()
        print("AWG + PSU OFF.")

    clk_vpp = vpp[clk_ch]
    print(f"\n  CLK pin{args.clk_pin}: VPP={clk_vpp:.2f} V")
    if clk_vpp < CLK_PRESENT_V:
        print(f"!!! CLOCK NOT PRESENT (VPP {clk_vpp:.2f}); check AWG CH1 on pin {args.clk_pin}.")
        return
    dmin, dmax, dvpp = vmin[data_ch], vmax[data_ch], vpp[data_ch]
    print(f"  DATA pin{args.data_pin}: VMAX={dmax:+.2f} VMIN={dmin:+.2f} VPP={dvpp:.2f} "
          f"(rail {args.rail:g} V)")
    print("\n==== RESULT ====")
    if dmin < args.thresh and dvpp > 1.0:
        print(f"*** DATA pin {args.data_pin} pulled LOW off the rail (VMIN {dmin:.2f} V) while "
              f"clocking pin {args.clk_pin} -> REAL open-collector DATA! ***")
        print(f"Analyze: python analyze_capture.py {OUTDIR}/{tag} "
              f"--clk-pin {args.clk_pin} --data-pin {args.data_pin}")
    else:
        print(f"DATA held near the {args.rail:g} V rail (VMIN {dmin:.2f} V) -> no driven bits on "
              f"pin {args.data_pin} with clk on pin {args.clk_pin}. Try other clk/data pins or "
              f"--mode burst.")


if __name__ == "__main__":
    main()
