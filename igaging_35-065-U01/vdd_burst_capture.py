"""Supply VDD to pin 1, then clock pin 2 and read DATA on pin 3 (PROTOCOL_RESEARCH.md hyp #3).

Leading hypothesis after all single-pin/burst/pull-down tests came up silent: the mic's
CLK/DATA *interface buffer* is powered from connector pin 1 (VDD), which the reader is meant
to supply (~3 V). The encoder+LCD run off the CR2032 (so the display works), but with pin 1
left floating the data interface is unpowered -> silence on every pin, exactly what we saw.
§11.3 measured pin 1 floating ~0 V, consistent with a VDD *input* (not an exposed rail).

Rig for this test (verified 2026-07-25):
    AWG CH1 -> 1 kOhm  -> pin 2  (clock)
    AWG CH2 -> 870 Ohm -> pin 1  (DC VDD supplied here)
    10 kOhm pull-down on pin 3 (DATA); scope CH1..3 on pins 1..3, CH4 on AWG CH1 out.

Two bugs in the first version of this file are fixed here:
  * VDD readback used an EDGE trigger through 0 V -> a flat DC line has no edge, so it never
    triggered and returned a stale 0.000 V. Now uses :MEASure VAVG (AUTO sweep). Diagnostic
    on 2026-07-25 confirmed pin1 tracks the command 1:1 (1.0->0.99, 3.0->3.00 V), no doubling.
  * The clock burst was not present in the captured window (scope timed out on a NORMal-sweep
    trigger and read garbage). Now: default CONTINUOUS clock (guaranteed to appear), AUTO-sweep
    capture (always yields a window), and a hard guard that the clock actually shows on the
    driven pin before any "no response" is believed.

SAFETY: CH2 is brought up at commanded 1.0 V FIRST and pin 1 is measured; if it reads >1.6 V
(=> voltage doubling / not High-Z) we abort before going higher. Everything is capped at
--max-volts (default 3.0 V, the battery ceiling) and driven through series resistors.

    python vdd_burst_capture.py --clk-pin 2 --data-pin 3
    python vdd_burst_capture.py --clk-pin 2 --data-pin 3 --mode burst
"""
import argparse
import os
import time

from scpi_lib import Scope, Awg
from clock_injection import digitize_transitions, PIN_CHANS, OUTDIR
from burst_capture import configure_burst, CROSSTALK, MARGIN

# Minimum vpp on the driven pin for the capture to count as "clock really present".
CLK_PRESENT_V = 1.5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clk-pin", type=int, default=2, choices=(1, 2, 3))
    ap.add_argument("--data-pin", type=int, default=3, choices=(1, 2, 3))
    ap.add_argument("--vdd", type=float, default=3.0, help="target VDD on pin 1 (V)")
    ap.add_argument("--amp", type=float, default=3.0, help="clock HIGH level (V)")
    ap.add_argument("--freq", type=float, default=9000)
    ap.add_argument("--mode", choices=("continuous", "burst"), default="continuous")
    ap.add_argument("--ncycles", type=int, default=21, help="burst mode: pulses per burst")
    ap.add_argument("--period-ms", type=float, default=10.0, help="burst mode: repeat period")
    ap.add_argument("--window-ms", type=float, default=4.0, help="scope window (ms)")
    ap.add_argument("--max-volts", type=float, default=3.0)
    args = ap.parse_args()
    if args.vdd > args.max_volts or args.amp > args.max_volts:
        raise SystemExit("vdd/amp exceeds --max-volts; refusing")

    drive_ch = PIN_CHANS[args.clk_pin]
    awg = Awg(); print("AWG IDN:", awg.query("*IDN?"))
    scope = Scope(); print("SCOPE IDN:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.8, offset=-2.0, coupling="DC")

    try:
        # --- Stage 1: safe VDD bring-up on pin 1 (CH2), measured via VAVG (not edge trig) ---
        awg.output(False, ch=1)  # clock off while we bring VDD up
        awg.dc(1.0, ch=2); awg.output(True, ch=2)
        time.sleep(0.4)
        v1 = scope.measure_vavg(1)
        print(f"\n[VDD check] commanded 1.0 V on pin1 -> scope reads {v1:.3f} V")
        if v1 > 1.6:
            raise SystemExit(f"pin1 ~2x commanded ({v1:.2f} V) => NOT High-Z / doubling. "
                             f"Aborting before raising voltage. Check :OUTPut2:LOAD.")
        awg.dc(args.vdd, ch=2)
        time.sleep(0.4)
        vv = scope.measure_vavg(1)
        sag = vv < args.vdd * 0.9
        print(f"[VDD check] commanded {args.vdd:g} V on pin1 -> scope reads {vv:.3f} V "
              f"({'SAGGING under load — interface drawing current' if sag else 'holding steady'})")

        # --- Stage 2: clock pin 2, capture pin 3 ---
        if args.mode == "burst":
            configure_burst(awg, args.freq, args.amp, args.ncycles, args.period_ms / 1000.0)
            tag = f"vdd_burst_p{args.clk_pin}"
            print(f"\nBURST clock: {args.ncycles} cyc @ {args.freq:g} Hz, {args.amp:g} V, "
                  f"pin {args.clk_pin}; VDD={args.vdd:g} V on pin1.")
        else:
            awg.square(args.freq, low=0.0, high=args.amp, ch=1)
            tag = f"vdd_cont_p{args.clk_pin}"
            print(f"\nCONTINUOUS clock: {args.freq:g} Hz, {args.amp:g} V on pin {args.clk_pin}; "
                  f"VDD={args.vdd:g} V on pin1.")
        awg.output(True, ch=1)
        time.sleep(0.3)

        # Decision is driven by LIVE :MEASure (re-evaluates every sweep, so an auto-repeating
        # burst is always caught) — NOT by digitising one RAW window, whose memory time-span can
        # be shorter than the 10 ms burst period and land entirely in the idle gap. Window must
        # span >1 burst period so a full train is always visible.
        win_ms = args.window_ms if args.mode == "continuous" else max(args.window_ms,
                                                                       args.period_ms * 2.5)
        scope.write(":TRIGger:SWEep AUTO"); scope.write(":RUN")
        scope.write(f":TIMebase:MAIN:SCALe {win_ms / 1000.0 / 10.0}")
        time.sleep(1.2)
        vpp = {ch: scope.measure_item(ch, "VPP") for ch in (1, 2, 3)}
        vtop = {ch: scope.measure_item(ch, "VTOP") for ch in (1, 2, 3)}
        vbase = {ch: scope.measure_item(ch, "VBASe") for ch in (1, 2, 3)}
        os.makedirs(OUTDIR, exist_ok=True)
        scope.screenshot(f"{OUTDIR}/{tag}_scope.png")
        # Best-effort raw record for later Phase-B analysis (may miss the burst; decision above
        # doesn't depend on it).
        try:
            scope.arm_single(trig_ch=drive_ch, level=args.amp * 0.5, mdepth=1_000_000,
                             tb_scale=win_ms / 1000.0 / 10.0, sweep="AUTO")
            scope.wait_stop(timeout=10)
            for ch in (1, 2, 3, 4):
                pre, raw = scope.read_raw(ch)
                with open(f"{OUTDIR}/{tag}_ch{ch}.bin", "wb") as f: f.write(raw)
                with open(f"{OUTDIR}/{tag}_ch{ch}.pre", "w") as f: f.write(pre)
        except Exception as e:
            print(f"  (raw record skipped: {e})")
    finally:
        try:
            awg.write(":SOURce1:BURSt:STATe OFF")
            awg.output(False, ch=1); awg.output(False, ch=2)
        except Exception:
            pass
        awg.close(); scope.close()
        print("AWG CH1+CH2 OFF.")

    clk_vpp = vpp[drive_ch]
    print(f"\n  CLK pin{args.clk_pin}: VPP={clk_vpp:.3f}V (VTOP={vtop[drive_ch]:.2f} "
          f"VBASe={vbase[drive_ch]:.2f})")

    # Guard: if the clock isn't really on the driven pin, this capture proves nothing.
    if clk_vpp < CLK_PRESENT_V:
        print(f"\n!!! CLOCK NOT CAPTURED (VPP {clk_vpp:.3f}V < {CLK_PRESENT_V}V expected ~{args.amp}V).")
        print("    The driven pin shows no clock, so any 'no response' below is meaningless.")
        print("    Check: CH1 lead on pin 2? series R intact? AWG CH1 actually output ON?")
        return

    base = CROSSTALK[args.clk_pin]
    hit = None
    for p in [q for q in PIN_CHANS if q != args.clk_pin]:
        pv, pt, pb = vpp[PIN_CHANS[p]], vtop[PIN_CHANS[p]], vbase[PIN_CHANS[p]]
        expect = base[p] * clk_vpp
        # Coupling swings SYMMETRICALLY about 0 (pt ~= -pb); a driven CMOS line sits on fixed
        # rails (asymmetric — offset from 0). Flag both amplitude AND shape.
        centered = abs(pt + pb) < 0.3 * pv if pv > 0.1 else True
        real = pv > expect * MARGIN and pv > 0.5 and not centered
        tagp = "DATA?" if p == args.data_pin else "watch"
        if p == 1:
            note = "  (pin1 = VDD rail; ignore)"
        elif real:
            note = "  <== ABOVE CROSSTALK & RAIL-CLAMPED — REAL DATA!"
        elif pv > expect * MARGIN and pv > 0.5:
            note = "  (large but symmetric about 0 — still coupling)"
        else:
            note = "  (crosstalk-level)"
        print(f"  {tagp} pin{p}: VPP={pv:.3f}V VTOP={pt:.2f} VBASe={pb:.2f} "
              f"(xtalk ~{expect:.2f}V){note}")
        if real and p != 1:
            hit = p

    print("\n==== SUMMARY ====")
    if hit:
        print(f"*** Pin {hit} drove real, rail-clamped data with pin 1 powered ({args.mode} clock) "
              f"-> CLK=pin{args.clk_pin}, DATA=pin{hit}, VDD=pin1. ***")
        print(f"Analyze: python analyze_capture.py {OUTDIR}/{tag} "
              f"--clk-pin {args.clk_pin} --data-pin {hit}")
    else:
        print(f"Clock confirmed present, VDD={vv:.2f}V on pin1, but pin{args.data_pin} stayed at "
              f"crosstalk level ({args.mode} clock). Did not wake the data interface.")
        if args.mode == "continuous":
            print("Next: try --mode burst (framing hypothesis), or a different clk/data pairing.")
        else:
            print("Next: burst idles HIGH — try idle-low, a different clk pin, or reconsider pin1=VDD.")


if __name__ == "__main__":
    main()
