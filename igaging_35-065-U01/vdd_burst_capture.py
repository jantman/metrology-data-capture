"""Supply VDD to pin 1, then burst-clock and read DATA (see PROTOCOL_RESEARCH.md hyp #3).

Leading hypothesis after all single-pin/burst/pull-down tests came up silent: the mic's
CLK/DATA *interface buffer* is powered from connector pin 1 (VDD), which the reader is meant
to supply (~3 V). The encoder+LCD run off the CR2032 (so the display works), but with pin 1
left floating the data interface is unpowered -> silence on every pin, exactly what we saw.
§11.3 measured pin 1 floating ~0 V, consistent with a VDD *input* (not an exposed rail).

Rig for this test:
    AWG CH1 -> 1 kOhm -> pin 2  (burst clock, as before)
    AWG CH2 -> series R -> pin 1 (DC VDD supplied here)
    10 kOhm pull-down on pin 3 (DATA); scope CH1..3 on pins 1..3, CH4 on AWG CH1 out.

SAFETY: CH2 is brought up at a commanded 1.0 V FIRST; pin 1's real level is read off the scope.
If it reads ~2 V (voltage doubling => not High-Z) we abort before going higher. Only after
confirming ~1:1 do we step CH2 to --vdd (default 3.0, hard-capped at --max-volts). Watching
pin 1 sag under load is a GOOD sign (the interface is drawing current = powering up).

    python vdd_burst_capture.py --clk-pin 2 --data-pin 3
    python vdd_burst_capture.py --clk-pin 2 --data-pin 3 --vdd 3.0
"""
import argparse
import os
import time

from scpi_lib import Scope, Awg
from clock_injection import digitize_transitions, PIN_CHANS, OUTDIR
from burst_capture import configure_burst, CROSSTALK, MARGIN


def chan_mean(pre, raw):
    """Mean (DC) voltage of a raw BYTE channel from its preamble scaling."""
    p = pre.split(",")
    yinc, yorig, yref = float(p[7]), float(p[8]), float(p[9])
    if not raw:
        return 0.0
    return sum((b - yorig - yref) * yinc for b in raw) / len(raw)


def read_pin1_level(scope):
    """Quick single capture just to read pin 1's DC level (VDD monitor)."""
    scope.arm_single(trig_ch=1, level=0.0, slope="POSitive", mdepth=100_000, tb_scale=0.005)
    scope.wait_stop(timeout=8)
    pre, raw = scope.read_raw(1)
    return chan_mean(pre, raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clk-pin", type=int, default=2, choices=(1, 2, 3))
    ap.add_argument("--data-pin", type=int, default=3, choices=(1, 2, 3))
    ap.add_argument("--vdd", type=float, default=3.0, help="target VDD on pin 1 (V)")
    ap.add_argument("--amp", type=float, default=3.0, help="clock HIGH level (V)")
    ap.add_argument("--freq", type=float, default=9000)
    ap.add_argument("--ncycles", type=int, default=21)
    ap.add_argument("--period-ms", type=float, default=10.0)
    ap.add_argument("--window-ms", type=float, default=40.0)
    ap.add_argument("--max-volts", type=float, default=3.0)
    args = ap.parse_args()
    if args.vdd > args.max_volts or args.amp > args.max_volts:
        raise SystemExit("vdd/amp exceeds --max-volts; refusing")

    drive_ch = PIN_CHANS[args.clk_pin]
    awg = Awg(); print("AWG IDN:", awg.query("*IDN?"))
    scope = Scope(); print("SCOPE IDN:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.5, offset=-1.5, coupling="DC")

    try:
        # --- Stage 1: safe VDD bring-up on pin 1 (CH2), verified on the scope ---
        awg.dc(1.0, ch=2)          # High-Z DC, commanded 1.0 V
        awg.output(True, ch=2)
        time.sleep(0.4)
        v = read_pin1_level(scope)
        print(f"\n[VDD check] commanded 1.0 V on pin1 -> scope reads {v:.3f} V")
        if v > 1.6:
            raise SystemExit(f"pin1 ~2x commanded ({v:.2f} V) => NOT High-Z / doubling. "
                             f"Aborting before raising voltage. Check :OUTPut2:LOAD.")
        if v < 0.5:
            print("  (pin1 well below 1.0 V — interface may be sinking current; that's OK, "
                  "continuing.)")
        awg.dc(args.vdd, ch=2)     # step to target VDD
        time.sleep(0.4)
        v = read_pin1_level(scope)
        print(f"[VDD check] commanded {args.vdd:g} V on pin1 -> scope reads {v:.3f} V "
              f"({'holding' if v > args.vdd*0.8 else 'SAGGING under load — interface drawing current!'})")

        # --- Stage 2: burst clock on CH1 and capture DATA ---
        configure_burst(awg, args.freq, args.amp, args.ncycles, args.period_ms / 1000.0)
        awg.output(True, ch=1)
        print(f"\nBURST clock ON: {args.ncycles} cyc @ {args.freq:g} Hz, {args.amp:g} V, "
              f"pin {args.clk_pin}; VDD={args.vdd:g} V on pin 1.")
        tb = args.window_ms / 1000.0 / 10.0
        tag = f"vdd_p{args.clk_pin}_{args.ncycles}c"
        scope.arm_single(trig_ch=drive_ch, level=args.amp * 0.5, slope="POSitive",
                         mdepth=1_000_000, tb_scale=tb)
        status = scope.wait_stop(timeout=15)
        os.makedirs(OUTDIR, exist_ok=True)
        vals = {}
        for ch in (1, 2, 3, 4):
            pre, raw = scope.read_raw(ch)
            with open(f"{OUTDIR}/{tag}_ch{ch}.bin", "wb") as f: f.write(raw)
            with open(f"{OUTDIR}/{tag}_ch{ch}.pre", "w") as f: f.write(pre)
            vals[ch] = digitize_transitions(pre, raw)
        scope.screenshot(f"{OUTDIR}/{tag}_scope.png")
    finally:
        try:
            awg.write(":SOURce1:BURSt:STATe OFF")
            awg.output(False, ch=1); awg.output(False, ch=2)
        except Exception:
            pass
        awg.close(); scope.close()
        print("AWG CH1+CH2 OFF (burst cleared).")

    print(f"\ntrigger status: {status}")
    clk_trans, clk_vpp = vals[drive_ch]
    print(f"  CLK pin{args.clk_pin}: {clk_trans} transitions, vpp={clk_vpp:.3f}V")
    base = CROSSTALK[args.clk_pin]
    hit = None
    for p in [q for q in PIN_CHANS if q != args.clk_pin]:
        trans, vpp = vals[PIN_CHANS[p]]
        expect = base[p] * clk_vpp
        real = vpp > expect * MARGIN and vpp > 0.5
        tagp = "DATA?" if p == args.data_pin else "watch"
        print(f"  {tagp} pin{p}: {trans} transitions, vpp={vpp:.3f}V"
              f"{'  <== ABOVE CROSSTALK — REAL DATA!' if real else '  (still crosstalk)'}")
        if real:
            hit = p
    print("\n==== SUMMARY ====")
    if hit:
        print(f"*** Pin {hit} drove real data once pin 1 was powered -> VDD hypothesis CONFIRMED. "
              f"CLK=pin{args.clk_pin}, DATA=pin{hit}, VDD=pin1. ***")
        print(f"Analyze: python analyze_capture.py {OUTDIR}/{tag} "
              f"--clk-pin {args.clk_pin} --data-pin {hit}")
    else:
        print("Still crosstalk even with pin 1 powered. If pin1 held VDD steady (no sag), the "
              "interface isn't powered from pin1 -> pin1 likely NC; reconsider clk/data pairing "
              "or a different enable. If pin1 sagged, it IS drawing current — try other clk pin.")


if __name__ == "__main__":
    main()
