"""CLOSED-CASE estimate of the mic's internal logic rail, by finding its input threshold.

The rail has been unmeasured since investigation §10 (`measure across C4/C5` — needs the board
open, which the FPC repair will not tolerate; see STATUS.md). This gets an estimate WITHOUT
opening anything, using the one reliable response we have.

METHOD: pin 1 strobes low whenever the DATA button is pressed AND edges arrive on pin 2 or
pin 3 (§11.15). That response is a working input receiver. So drive an input with a square wave
and RAMP THE AMPLITUDE DOWN until the mic stops responding. A CMOS input threshold sits near
0.5 x VDD, so the cut-off implies the rail — read against the MEASURED level at the pin, not the
commanded amplitude (see pin_high_level; the 10k pull-up lifts it):

    pin high at cut-off ~1.5 V  =>  rail ~3.0 V      ~0.9 V  =>  rail ~1.8 V
    pin high at cut-off ~1.2 V  =>  rail ~2.4 V      ~0.8 V  =>  rail ~1.6 V

This also settles whether the blanket 3 V pull-up rail used in every test so far has been
over-driving the inputs (review.md §5.2).

DESIGN NOTES (both are lessons from review.md):
  * Detection uses an ARMED single-shot trigger (NORMal sweep) that watches continuously, NOT
    the VMIN polling loop that covers only ~4-12% of wall-clock time and produced the §11.12
    false negative.
  * Each amplitude verifies the clock is actually present on the driven pin before arming, so a
    dead AWG lead cannot masquerade as "below threshold" (the §11.8 guard).
  * Amplitude only ever DECREASES from 3.0 V, so there is no over-drive risk.
  * A control re-test at the starting amplitude runs at the end: if the mic stops responding
    there too, it slept / the button failed / the rig moved, and the whole run is void.

WIRING (same rig as two_input_capture.py, minus AWG CH2):
    PSU +3 V -> 10k -> each of pins 1/2/3      AWG CH1 -> 1k -> --clk-pin
    scope CH1/2/3 on pins 1/2/3, CH4 on AWG CH1 out
    PSU- and all grounds -> pin 4
Mic AWAKE, battery IN, case closed.

Run it yourself so you see the prompts live:

    ! python threshold_sweep.py
    ! python threshold_sweep.py --clk-pin 3        # confirm on the other input
"""
import argparse
import datetime
import os
import time

from scpi_lib import Scope, Awg
from psu_lib import PSU
from clock_injection import PIN_CHANS

OUTDIR = "findings"
# Extends well below the first sweep's 0.6 V floor. NOTE the hard limit: the 10k pull-up holds
# the driven pin's LOW at rail/11 ~= 0.27 V, so pin_high can never go below that and the swing
# collapses as the command approaches 0. If the threshold is not bracketed by ~0.15 V commanded,
# the pull-up on the driven pin has to come off to get a true 0->amp swing (see the verdict).
DEFAULT_AMPS = [3.0, 2.5, 2.0, 1.6, 1.4, 1.2, 1.0, 0.9, 0.8, 0.7, 0.6,
                0.5, 0.4, 0.3, 0.25, 0.2, 0.15]


def pin_high_level(scope, ch):
    """The driven pin's actual logic-HIGH level in volts.

    IMPORTANT: this is NOT the commanded amplitude. The AWG drives through a 1k series
    resistor into a pin that carries a 10k pull-up to the +3 V rail, so the two form a
    divider and the rail lifts both levels:

        pin_high = (10*amp + 3) / 11      pin_low = 3 * 1/11 ~= 0.27 V

    i.e. a commanded 1.0 V actually presents ~1.18 V at the pin. The threshold inference
    has to use the measured level, not the command, or it is wrong by up to ~30%.

    Prefers VTOP (settled high) and falls back to VMAX (raw peak) if VTOP returns the
    "not ready" sentinel — VMAX exaggerates noise (§11.9/§11.12) so it is second choice.
    """
    try:
        return scope.measure_item(ch, "VTOP"), "VTOP"
    except RuntimeError:
        return scope.measure_item(ch, "VMAX"), "VMAX"


def clock_present(scope, ch, amp):
    """True if the driven pin really carries the commanded square wave. Returns (ok, vpp, high)."""
    vpp = scope.measure_item(ch, "VPP")
    high, _src = pin_high_level(scope, ch)
    # expected swing at the pin after the 1k/10k divider, ~10% tolerance
    return vpp >= max(0.25, amp * 0.9 * 0.6), vpp, high


def try_amplitude(scope, awg, args, amp, clk_ch, data_ch, label=""):
    """Set amplitude, verify the clock, arm on pin-1 falling, wait.

    Returns (responded, vpp, pin_high) — pin_high is the MEASURED high level at the pin,
    which is what the threshold inference must use (see pin_high_level)."""
    awg.set_high_level(amp, ch=1)
    time.sleep(0.4)

    scope.write(":TRIGger:SWEep AUTO")
    scope.write(":RUN")
    scope.write(":TIMebase:MAIN:SCALe 0.0005")
    time.sleep(0.8)
    ok, vpp, high = clock_present(scope, clk_ch, amp)
    if not ok:
        print(f"  !! clock NOT present on pin {args.clk_pin} (VPP {vpp:.2f} V vs commanded "
              f"{amp:.2f} V) — check the AWG lead. Result for this step is VOID.")
        return None, vpp, high

    scope.arm_single(trig_ch=data_ch, level=args.thresh, slope="NEGative",
                     mdepth=10_000, tb_scale=args.cap_tb_us / 1e6, sweep="NORMal")
    print(f"  {label}cmd={amp:>4.2f} V -> pin{args.clk_pin} HIGH={high:.2f} V (VPP {vpp:.2f}) — "
          f"TAP THE DATA BUTTON for the next {args.window:.0f}s...", flush=True)
    status = scope.wait_stop(timeout=args.window)
    responded = status == "STOP"
    print(f"     -> {'RESPONDED (pin 1 pulled low)' if responded else 'no response'}")
    return responded, vpp, high


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clk-pin", type=int, default=2, choices=(2, 3),
                    help="which INPUT pin to drive (pin 1 is the mic's output)")
    ap.add_argument("--data-pin", type=int, default=1, choices=(1, 2, 3))
    ap.add_argument("--freq", type=float, default=1000.0)
    ap.add_argument("--amplitudes", type=str, default=None, help="comma list, descending")
    ap.add_argument("--window", type=float, default=12.0, help="seconds to watch per amplitude")
    ap.add_argument("--thresh", type=float, default=1.5, help="pin-1 falling trigger level (V)")
    ap.add_argument("--cap-tb-us", type=float, default=5000.0)
    ap.add_argument("--rail", type=float, default=3.0)
    ap.add_argument("--ilim", type=float, default=0.02)
    ap.add_argument("--ovp", type=float, default=3.6)
    ap.add_argument("--max-volts", type=float, default=3.0)
    args = ap.parse_args()

    amps = ([float(x) for x in args.amplitudes.split(",")] if args.amplitudes
            else list(DEFAULT_AMPS))
    if any(a > args.max_volts for a in amps):
        raise SystemExit(f"amplitude exceeds --max-volts {args.max_volts}; refusing")
    if sorted(amps, reverse=True) != amps:
        raise SystemExit("amplitudes must be descending (we only ever ramp DOWN)")

    clk_ch, data_ch = PIN_CHANS[args.clk_pin], PIN_CHANS[args.data_pin]
    psu = PSU()
    awg = Awg(); print("AWG:", awg.query("*IDN?"))
    scope = Scope(); print("SCOPE:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.8, offset=-2.0, coupling="DC")

    rows = []
    control = None
    neg_control = None
    try:
        psu.bring_up(args.rail, args.ilim, ovp=args.ovp)
        awg.square(args.freq, low=0.0, high=amps[0], ch=1)
        awg.output(True, ch=1)
        time.sleep(0.4)
        print(f"\nDriving pin {args.clk_pin} at {args.freq:g} Hz; watching pin {args.data_pin} "
              f"for a falling edge through {args.thresh} V.")
        print(f"Pull-ups on all three pins at {args.rail:g} V.\n")
        print(">>> KEEP TAPPING THE DATA BUTTON throughout — about "
              f"{len(amps) * (args.window + 3) / 60:.0f} minutes. <<<\n")

        for amp in amps:
            responded, vpp, high = try_amplitude(scope, awg, args, amp, clk_ch, data_ch)
            rows.append((amp, responded, vpp, high))
            if responded is False and len([r for r in rows if r[1] is False]) >= 2:
                print("  (two consecutive non-responses — stopping the descent)")
                break

        print("\n--- POSITIVE CONTROL: back to the starting amplitude ---")
        control, _, _ = try_amplitude(scope, awg, args, amps[0], clk_ch, data_ch, label="CONTROL ")

        # NEGATIVE CONTROL — the one that decides whether any of the above means anything.
        # If pin 1 still strobes with NO clock at all, then the response is not gated on the
        # driven input and the whole sweep measures nothing about an input threshold.
        print("\n--- NEGATIVE CONTROL: AWG OFF, button only ---")
        awg.output(False, ch=1)
        time.sleep(0.5)
        scope.arm_single(trig_ch=data_ch, level=args.thresh, slope="NEGative",
                         mdepth=10_000, tb_scale=args.cap_tb_us / 1e6, sweep="NORMal")
        print(f"  NEGCTRL clock OFF — KEEP TAPPING for {args.window:.0f}s. Expected: NO response.",
              flush=True)
        neg_control = scope.wait_stop(timeout=args.window) == "STOP"
        print(f"     -> {'RESPONDED (!!)' if neg_control else 'no response (as expected)'}")
    finally:
        try:
            awg.output(False, ch=1)
        except Exception:
            pass
        psu.off(); awg.close(); scope.close()
        print("\nAWG + PSU OFF.")

    print("\n==== RESULTS ====")
    print("  commanded | measured pin HIGH | result")
    for amp, responded, vpp, high in rows:
        mark = {True: "RESPONDED", False: "no response", None: "VOID (no clock)"}[responded]
        print(f"  {amp:>6.2f} V  | {high:>10.2f} V      | {mark}")

    print("\n==== VERDICT ====")
    if neg_control is True:
        print("  *** NEGATIVE CONTROL FAILED — pin 1 strobed with the clock switched OFF. ***")
        print("      The response is NOT gated on the driven input, so this sweep measures")
        print("      nothing about an input threshold and every 'RESPONDED' above is suspect.")
        print("      It also contradicts §11.12/§11.15, where the button alone did nothing —")
        print("      so something in the rig or the trigger condition has changed. Investigate")
        print("      before drawing any conclusion. THE RUN IS VOID.")
    elif control is not True:
        print("  *** CONTROL FAILED — the mic did not respond at the starting amplitude on the")
        print("      re-test. It may have slept, the button may not have been pressed, or the rig")
        print("      moved. THE WHOLE RUN IS VOID. Wake the mic and re-run. ***")
    else:
        # Use the MEASURED pin high level, not the commanded amplitude (see pin_high_level).
        good = [h for _a, r, _v, h in rows if r is True]
        bad = [h for _a, r, _v, h in rows if r is False]
        if good and bad and min(good) > max(bad):
            lo, hi = max(bad), min(good)
            rail_lo, rail_hi = 2 * lo, 2 * hi
            print(f"  Threshold is between a measured pin high of {lo:.2f} V (no response) and "
                  f"{hi:.2f} V (response).")
            print(f"  At ~0.5 x VDD that implies an internal rail of roughly "
                  f"{rail_lo:.1f}-{rail_hi:.1f} V.")
            if rail_hi <= 2.2:
                print("  => LOW-VOLTAGE PART. The 3 V pull-up rail used in every test so far has")
                print("     been ABOVE the mic's own rail — redo the key pull-up tests at this")
                print("     level before trusting any earlier 'held at the rail' negative.")
            else:
                print("  => consistent with a ~3 V rail; the 3 V pull-up rail was appropriate.")
        elif good and not bad:
            floor = args.rail / 11.0
            print(f"  Responded at EVERY amplitude, down to a measured pin high of "
                  f"{min(good):.2f} V.")
            print(f"  => the input threshold is BELOW {min(good):.2f} V, so at ~0.5 x VDD the "
                  f"internal rail is below ~{2 * min(good):.1f} V.")
            print(f"  That already means the mic is NOT a 3 V-logic part, and the blanket 3 V")
            print(f"  pull-up rail used in every test to date has been ABOVE its own rail.")
            if min(good) - floor < 0.25:
                print(f"\n  *** FLOOR REACHED: the 10k pull-up pins the driven pin's LOW at")
                print(f"      rail/11 = {floor:.2f} V, so the swing has collapsed to "
                      f"{min(good) - floor:.2f} V and going lower is meaningless.")
                print(f"      To push further, REMOVE THE 10k PULL-UP FROM PIN {args.clk_pin} ONLY")
                print(f"      (leave pins 1 and 3 pulled up) for a true 0->amp swing, and re-run.")
            else:
                print(f"  Re-run with lower --amplitudes to bracket it "
                      f"(floor is {floor:.2f} V — see the note on DEFAULT_AMPS).")
        else:
            print("  No clean transition found; results inconsistent. Re-run.")

    os.makedirs(OUTDIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = f"{OUTDIR}/threshold_sweep_{stamp}.txt"
    with open(path, "w") as f:
        f.write(f"input-threshold sweep, clk pin {args.clk_pin} @ {args.freq:g} Hz, "
                f"pull-ups {args.rail:g} V\n{stamp}\n\n")
        f.write("commanded  pin_high  vpp   result\n")
        for amp, responded, vpp, high in rows:
            f.write(f"{amp:>6.2f} V  {high:>6.2f} V  {vpp:5.2f}  "
                    f"{ {True:'RESPONDED', False:'no', None:'VOID'}[responded] }\n")
        f.write(f"\npositive control (re-test at {amps[0]:.2f} V): "
                f"{ {True:'RESPONDED', False:'NO — RUN VOID', None:'VOID'}[control] }\n")
        f.write(f"negative control (AWG OFF, button only): "
                f"{ {True:'RESPONDED — RUN VOID', False:'no response (expected)',
                     None:'not run'}[neg_control] }\n")
    print(f"\nsaved -> {path}")


if __name__ == "__main__":
    main()
