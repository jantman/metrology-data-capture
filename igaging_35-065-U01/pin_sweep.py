"""Pin-permutation sweep — the definitive CLK/DATA/VDD identification (Phase A).

Every stimulus on the assumed pin2=CLK/pin3=DATA mapping has been silent, so verify the one
thing never actually tested: WHICH pin is CLK vs DATA vs VDD. This drives one pin as the clock
and (optionally) one as VDD, and watches the remaining pin(s) for a RAIL-CLAMPED (driven)
response — as opposed to the symmetric-about-0 capacitive coupling we've seen everywhere.

You move two AWG leads between runs; the scope stays put (CH1..3 on connector pins 1..3, CH4 on
AWG CH1 out). Per combo:
    AWG CH1 (clock, via 1k)  -> connector pin  --clk-pin
    AWG CH2 (VDD, via 870R)  -> connector pin  --vdd-pin   (omit / 0 = no VDD)
    10k pull-down            -> the WATCHED pin (the remaining one)
    all grounds -> pin 4

    python pin_sweep.py --clk-pin 1 --vdd-pin 2      # drive clk on 1, VDD on 2, watch 3
    python pin_sweep.py --clk-pin 3 --vdd-pin 1 --mode burst

Suggested matrix (each watches the third pin); clk2/vdd1 is already known-negative:
    clk1 vdd2 | clk1 vdd3 | clk2 vdd3 | clk3 vdd1 | clk3 vdd2
"""
import argparse
import os
import time

from scpi_lib import Scope, Awg
from clock_injection import PIN_CHANS, OUTDIR
from burst_capture import configure_burst

CLK_PRESENT_V = 1.5
XTALK_RATIO = 0.25   # measured pin/clk coupling ~0.22; use a hair above as the ceiling
MARGIN = 1.8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clk-pin", type=int, required=True, choices=(1, 2, 3))
    ap.add_argument("--vdd-pin", type=int, default=0, choices=(0, 1, 2, 3), help="0 = no VDD")
    ap.add_argument("--vdd", type=float, default=3.0)
    ap.add_argument("--amp", type=float, default=3.0)
    ap.add_argument("--freq", type=float, default=9000)
    ap.add_argument("--mode", choices=("continuous", "burst"), default="continuous")
    ap.add_argument("--ncycles", type=int, default=21)
    ap.add_argument("--period-ms", type=float, default=10.0)
    ap.add_argument("--max-volts", type=float, default=3.0)
    args = ap.parse_args()
    if args.vdd_pin == args.clk_pin:
        raise SystemExit("clk-pin and vdd-pin must differ")
    if args.vdd > args.max_volts or args.amp > args.max_volts:
        raise SystemExit("vdd/amp exceeds --max-volts")

    clk_ch = PIN_CHANS[args.clk_pin]
    watch = [p for p in (1, 2, 3) if p != args.clk_pin]
    awg = Awg(); print("AWG IDN:", awg.query("*IDN?"))
    scope = Scope(); print("SCOPE IDN:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.8, offset=-2.0, coupling="DC")

    vv = None
    try:
        if args.vdd_pin:
            awg.dc(1.0, ch=2); awg.output(True, ch=2); time.sleep(0.4)
            v = scope.measure_vavg(PIN_CHANS[args.vdd_pin])
            print(f"[VDD] 1.0 V commanded on pin{args.vdd_pin} -> reads {v:.3f} V")
            if v > 1.6:
                raise SystemExit(f"pin{args.vdd_pin} ~2x commanded ({v:.2f}) => doubling; abort.")
            awg.dc(args.vdd, ch=2); time.sleep(0.4)
            vv = scope.measure_vavg(PIN_CHANS[args.vdd_pin])
            print(f"[VDD] {args.vdd:g} V commanded on pin{args.vdd_pin} -> reads {vv:.3f} V")

        if args.mode == "burst":
            configure_burst(awg, args.freq, args.amp, args.ncycles, args.period_ms / 1000.0)
        else:
            awg.square(args.freq, low=0.0, high=args.amp, ch=1)
        awg.output(True, ch=1); time.sleep(0.4)
        print(f"\n{args.mode} clock {args.freq:g} Hz, {args.amp:g} V on pin {args.clk_pin}"
              f"{'; VDD ' + str(args.vdd) + 'V on pin ' + str(args.vdd_pin) if args.vdd_pin else '; no VDD'}.")

        win_ms = 4.0 if args.mode == "continuous" else args.period_ms * 2.5
        scope.write(":TRIGger:SWEep AUTO"); scope.write(":RUN")
        scope.write(f":TIMebase:MAIN:SCALe {win_ms / 1000.0 / 10.0}")
        time.sleep(1.2)
        vpp = {ch: scope.measure_item(ch, "VPP") for ch in (1, 2, 3)}
        vtop = {ch: scope.measure_item(ch, "VTOP") for ch in (1, 2, 3)}
        vbase = {ch: scope.measure_item(ch, "VBASe") for ch in (1, 2, 3)}
        os.makedirs(OUTDIR, exist_ok=True)
        tag = f"sweep_clk{args.clk_pin}_vdd{args.vdd_pin}_{args.mode}"
        scope.screenshot(f"{OUTDIR}/{tag}_scope.png")
    finally:
        try:
            awg.write(":SOURce1:BURSt:STATe OFF")
            awg.output(False, ch=1); awg.output(False, ch=2)
        except Exception:
            pass
        awg.close(); scope.close()
        print("AWG CH1+CH2 OFF.")

    clk_vpp = vpp[clk_ch]
    print(f"\n  CLK pin{args.clk_pin}: VPP={clk_vpp:.2f}V (VTOP {vtop[clk_ch]:+.2f}/"
          f"VBASe {vbase[clk_ch]:+.2f})")
    if clk_vpp < CLK_PRESENT_V:
        print(f"\n!!! CLOCK NOT PRESENT (VPP {clk_vpp:.2f} < {CLK_PRESENT_V}). Is AWG CH1 on "
              f"pin {args.clk_pin}? Result void.")
        return

    hit = None
    for p in watch:
        role = "VDD" if p == args.vdd_pin else "DATA?"
        pv, pt, pb = vpp[PIN_CHANS[p]], vtop[PIN_CHANS[p]], vbase[PIN_CHANS[p]]
        expect = XTALK_RATIO * clk_vpp
        centered = abs(pt + pb) < 0.3 * pv if pv > 0.1 else True
        real = role == "DATA?" and pv > expect * MARGIN and pv > 0.5 and not centered
        if role == "VDD":
            note = "  (VDD rail; ignore)"
        elif real:
            note = "  <== RAIL-CLAMPED DRIVEN DATA!"
        elif pv > expect * MARGIN and pv > 0.5:
            note = "  (large but symmetric about 0 -> coupling)"
        else:
            note = "  (coupling)"
        print(f"  pin{p} [{role}]: VPP={pv:.2f}V VTOP={pt:+.2f} VBASe={pb:+.2f}{note}")
        if real:
            hit = p

    print("\n==== SUMMARY ====")
    if hit:
        print(f"*** DATA found on pin {hit}! CLK=pin{args.clk_pin}"
              f"{', VDD=pin' + str(args.vdd_pin) if args.vdd_pin else ''}. "
              f"Proceed to Phase B (analyze_capture.py). ***")
    else:
        print(f"No driven data (clk=pin{args.clk_pin}, vdd=pin{args.vdd_pin or 'none'}, "
              f"{args.mode}). Try the next combo.")


if __name__ == "__main__":
    main()
