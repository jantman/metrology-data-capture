"""Burst-mode clock injection (see PROTOCOL_RESEARCH.md hypothesis #1).

Real iGaging 21-bit readers (Yuriy's Toys, Rysium) do NOT clock continuously — they emit
**21 clock pulses (~2.33 ms) then an idle gap (~7 ms)** and repeat (~100-150 Hz). Our earlier
continuous 9 kHz injection produced only crosstalk; the mic likely frames on the idle gap and
never starts mid-stream. This drives the AWG in N-cycle burst mode with an inter-burst gap and
watches the DATA candidate for a frame-aligned response.

Pair with a 10-22 kOhm pull-down on the DATA pin (research hypothesis #2): it kills the
capacitive crosstalk on that floating line so a real, actively-driven data burst stands out.

Reference mapping for THIS self-powered unit: CLOCK = pin 2, DATA = pin 3 (pin 1 unused).

    python burst_capture.py --clk-pin 2 --data-pin 3
    python burst_capture.py --clk-pin 2 --data-pin 3 --ncycles 24 --period-ms 12

Idle LOW clock, ~3.0 V, safe (High-Z, series R, 3 V ceiling). Saves captures/burst_* for
analyze_capture.py.
"""
import argparse
import os
import time

from scpi_lib import Scope, Awg
from clock_injection import digitize_transitions, PIN_CHANS, OUTDIR

# Continuous-clock crosstalk baseline (non-driven pin vpp / clock vpp) from Phase A.
CROSSTALK = {1: {2: 0.21, 3: 0.11}, 2: {1: 0.18, 3: 0.21}, 3: {1: 0.11, 2: 0.21}}
MARGIN = 1.8


def configure_burst(awg, freq, amp, ncycles, period_s):
    """DG902 Pro N-cycle burst, internal auto-repeat. Verified SCPI (2026-07-17)."""
    awg.set_highz(1)
    awg.write(":SOURce1:FUNCtion SQUare")
    awg.write(f":SOURce1:FREQuency {freq}")
    awg.write(":SOURce1:VOLTage:LOW 0")
    awg.write(f":SOURce1:VOLTage:HIGH {amp}")
    awg.write(":SOURce1:BURSt:STATe ON")
    awg.write(":SOURce1:BURSt:MODE TRIGgered")
    awg.write(f":SOURce1:BURSt:NCYCles {ncycles}")
    awg.write(f":SOURce1:BURSt:INTernal:PERiod {period_s}")
    awg.write(":TRIGger1:SOURce IMMediate")  # auto-repeat bursts at the internal period


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clk-pin", type=int, required=True, choices=(1, 2, 3))
    ap.add_argument("--data-pin", type=int, default=None, choices=(1, 2, 3),
                    help="pin to highlight as DATA (default: report all non-driven)")
    ap.add_argument("--amp", type=float, default=3.0)
    ap.add_argument("--freq", type=float, default=9000)
    ap.add_argument("--ncycles", type=int, default=21, help="clock pulses per burst (21-bit frame)")
    ap.add_argument("--period-ms", type=float, default=10.0, help="burst repeat period (ms)")
    ap.add_argument("--window-ms", type=float, default=40.0, help="scope window (ms)")
    ap.add_argument("--max-volts", type=float, default=3.0)
    args = ap.parse_args()
    if args.amp > args.max_volts:
        raise SystemExit(f"amp {args.amp} exceeds --max-volts {args.max_volts}")

    drive_ch = PIN_CHANS[args.clk_pin]
    watch = [p for p in PIN_CHANS if p != args.clk_pin]
    base = CROSSTALK[args.clk_pin]

    awg = Awg(); print("AWG IDN:", awg.query("*IDN?"))
    scope = Scope(); print("SCOPE IDN:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.5, offset=-1.5, coupling="DC")

    configure_burst(awg, args.freq, args.amp, args.ncycles, args.period_ms / 1000.0)
    awg.output(True)
    print(f"\nBURST clock ON: {args.ncycles} cyc @ {args.freq:g} Hz, {args.amp:g} V idle-LOW, "
          f"every {args.period_ms:g} ms, driving pin {args.clk_pin}.")

    tb = args.window_ms / 1000.0 / 10.0
    tag = f"burst_p{args.clk_pin}_{args.ncycles}c"
    try:
        scope.arm_single(trig_ch=drive_ch, level=args.amp * 0.5, slope="POSitive",
                         mdepth=1_000_000, tb_scale=tb)
        status = scope.wait_stop(timeout=15)
        os.makedirs(OUTDIR, exist_ok=True)
        vals = {}
        for ch in (1, 2, 3, 4):
            pre, raw = scope.read_raw(ch)
            with open(f"{OUTDIR}/{tag}_ch{ch}.bin", "wb") as f: f.write(raw)
            with open(f"{OUTDIR}/{tag}_ch{ch}.pre", "w") as f: f.write(pre)
            trans, vpp = digitize_transitions(pre, raw)
            vals[ch] = (trans, vpp)
        scope.screenshot(f"{OUTDIR}/{tag}_scope.png")
    finally:
        awg.write(":SOURce1:BURSt:STATe OFF")  # restore continuous mode for other tools
        awg.output(False)
        awg.close(); scope.close()
        print("AWG output OFF (burst mode cleared).")

    print(f"\ntrigger status: {status}")
    clk_trans, clk_vpp = vals[drive_ch]
    print(f"  CLK pin{args.clk_pin}: {clk_trans} transitions, vpp={clk_vpp:.3f}V")
    hit = None
    for p in watch:
        trans, vpp = vals[PIN_CHANS[p]]
        expect = base[p] * clk_vpp
        ratio = vpp / clk_vpp if clk_vpp else 0
        real = vpp > expect * MARGIN and vpp > 0.5
        star = args.data_pin == p
        print(f"  {'DATA?' if star else 'watch'} pin{p}: {trans} transitions, vpp={vpp:.3f}V "
              f"(x{ratio:.2f} of clk){'  <== ABOVE CROSSTALK — REAL!' if real else ''}")
        if real:
            hit = p
    print("\n==== SUMMARY ====")
    if hit:
        print(f"Pin {hit} responded above crosstalk while bursting pin {args.clk_pin} -> DATA.")
        print(f"Analyze: python analyze_capture.py {OUTDIR}/{tag} "
              f"--clk-pin {args.clk_pin} --data-pin {hit}")
    else:
        print(f"Still only crosstalk on {watch}. Burst framing alone didn't wake it "
              f"(driving pin {args.clk_pin}). Next: confirm pull-down present, or try pin-1 "
              f"enable / other clk pin.")


if __name__ == "__main__":
    main()
