"""Button-gated clock-injection probe (see BRINGUP_PLAN.md Phase A fallback).

Hypothesis: the mic only drives DATA while its front-panel *Data/Hold* button is held
(an output-enable gate). Phase A drove a continuous clock into each pin and saw only
crosstalk (every non-driven pin swung a FIXED FRACTION of the clock amplitude -> passive
coupling, mic driving nothing). If a button gates the output, then holding it while we clock
should make the real DATA pin jump ABOVE its crosstalk fraction / clamp to the logic rail.

This drives a continuous square clock on --clk-pin at a single amplitude and takes N single-shot
4-channel captures ~1 s apart, so you can hold the button through the whole window without
timing anything. For each capture it prints per-pin vpp and, for the two non-driven pins,
compares the observed swing to the crosstalk baseline measured in Phase A. A non-driven pin
whose swing clearly exceeds its baseline (or that carries a non-clock frame) is the mic
actually talking -> that pin is DATA.

    python button_capture.py --clk-pin 3            # lead on pin 3; hold Data button while it runs
    python button_capture.py --clk-pin 3 --amp 3.0 --n 10

Saves every capture as captures/btn_p<clk>_<amp>v_r<round>_ch{1..4}.{bin,pre} so any promising
round can be fed straight to analyze_capture.py.
"""
import argparse
import os
import time

from scpi_lib import Scope, Awg
from clock_injection import digitize_transitions, PIN_CHANS, OUTDIR

# Crosstalk baseline from Phase A (non-driven pin vpp / clock vpp), by driven pin.
# Used only to flag "this is more than coupling" — a generous margin avoids false positives.
CROSSTALK = {
    1: {2: 0.21, 3: 0.11},
    2: {1: 0.18, 3: 0.21},
    3: {1: 0.11, 2: 0.21},
}
MARGIN = 1.8  # a pin must exceed baseline*clock*MARGIN to be called a real response


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clk-pin", type=int, required=True, choices=(1, 2, 3),
                    help="connector pin the AWG lead is physically driving")
    ap.add_argument("--amp", type=float, default=3.0, help="clock HIGH level V (<= 3.0)")
    ap.add_argument("--freq", type=float, default=9000)
    ap.add_argument("--n", type=int, default=12, help="number of captures over the hold window")
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
    awg.square(freq=args.freq, low=0.0, high=args.amp, duty=50)
    awg.output(True)
    print(f"\nClock ON: {args.freq:g} Hz, {args.amp:g} V, driving pin {args.clk_pin}.")
    print(f">>> HOLD the mic's Data button NOW and keep holding until this finishes ({args.n} caps).\n")

    os.makedirs(OUTDIR, exist_ok=True)
    hits = []
    try:
        for r in range(args.n):
            tag = f"btn_p{args.clk_pin}_{args.amp:g}v_r{r}"
            scope.arm_single(trig_ch=drive_ch, level=args.amp * 0.5, slope="POSitive",
                             mdepth=1_000_000, tb_scale=0.005)
            scope.wait_stop(timeout=15)
            vals = {}
            for ch in (1, 2, 3, 4):
                pre, raw = scope.read_raw(ch)
                with open(f"{OUTDIR}/{tag}_ch{ch}.bin", "wb") as f: f.write(raw)
                with open(f"{OUTDIR}/{tag}_ch{ch}.pre", "w") as f: f.write(pre)
                _, vpp = digitize_transitions(pre, raw)
                vals[ch] = vpp
            clk_vpp = vals[drive_ch]
            flags = []
            for p in watch:
                obs = vals[PIN_CHANS[p]]
                expect = base[p] * clk_vpp
                ratio = obs / clk_vpp if clk_vpp else 0
                real = obs > expect * MARGIN and obs > 0.5
                flags.append(f"pin{p}={obs:.3f}V(x{ratio:.2f}{' REAL!' if real else ''})")
                if real:
                    hits.append((r, p, obs))
            print(f"  r{r}: clk(pin{args.clk_pin})={clk_vpp:.3f}V  " + "  ".join(flags))
            time.sleep(1.0)
    finally:
        awg.output(False)
        awg.close(); scope.close()
        print("\nAWG output OFF.")

    print("\n==== SUMMARY ====")
    if hits:
        best = max(hits, key=lambda h: h[2])
        print(f"REAL response: pin {best[1]} swung {best[2]:.3f} V (round {best[0]}) — "
              f"that's DATA, gated by the button. CLK = pin {args.clk_pin}.")
        print(f"Analyze: python analyze_capture.py "
              f"captures/btn_p{args.clk_pin}_{args.amp:g}v_r{best[0]} "
              f"--clk-pin {args.clk_pin} --data-pin {best[1]}")
    else:
        print(f"No above-crosstalk response on pins {watch} while driving pin {args.clk_pin}.")
        print("Either the button isn't the gate here, or pin "
              f"{args.clk_pin} isn't CLK — move the lead and retry, or try --freq lower.")


if __name__ == "__main__":
    main()
