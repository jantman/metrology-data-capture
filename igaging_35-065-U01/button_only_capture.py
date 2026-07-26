"""Button-alone capture: pull-ups on, NOTHING driven, watch all three pins on a DATA press.

WHY THIS EXISTS. The threshold sweep's negative control fired: pin 1 strobed with the AWG
switched off entirely. That contradicts §11.15's "the trigger is (button) AND (edges on pin 2 or
pin 3) — both required", whose button-alone leg came from §11.12 Test 1 — a run whose detection
was the VMIN polling loop that covers only ~4-12%% of wall-clock time (review.md §1.3). A null
from that loop is not evidence of absence, so "button alone does nothing" may simply have been
another false negative from the same defect.

But a trigger is not a frame. §11.8 recorded a NORMal trigger firing once on a "mechanical/EMI
press glitch" whose RAW readback was flat. So this captures the WAVEFORM and discriminates:

    real strobe  -> pin 1 sits low for hundreds of consecutive samples (~ms)
    press glitch -> one or two isolated samples cross the threshold

SECOND, EQUALLY IMPORTANT PURPOSE. Every "are pins 2/3 ever driven?" check so far had a clock on
one of them, which MASKS any device drive on that pin, and §11.16 only ever captured 2 of the 4
unmasked cells. With no clock at all, ALL THREE pins are unmasked simultaneously for the first
time. If the mic transmits anything on a button press — a Digimatic-style CK+DATA pair, say —
this is the capture that would show it.

WIRING (unchanged from the threshold sweep, minus the AWG — leave the AWG lead connected, it is
switched off in software):
    PSU +3 V -> 10k -> each of pins 1/2/3      scope CH1/2/3 on pins 1/2/3
    PSU- and all grounds -> pin 4 (+ pin 5)
Mic AWAKE, battery IN, case closed.

    python button_only_capture.py                 # 3 events, 50 ms window
    python button_only_capture.py --reps 5 --cap-tb-us 20000    # slower/wider
"""
import argparse
import datetime
import os
import time

from scpi_lib import Scope, Awg
from psu_lib import PSU
from clock_injection import PIN_CHANS, OUTDIR

FINDINGS = "findings"


def scale(pre, raw):
    p = pre.split(",")
    xinc = float(p[4])
    yinc, yorig, yref = float(p[7]), float(p[8]), float(p[9])
    return xinc, [(b - yorig - yref) * yinc for b in raw]


def runs_below(vals, thresh):
    """Longest run of consecutive samples below `thresh`, and the total count below."""
    best = cur = total = 0
    for v in vals:
        if v < thresh:
            cur += 1
            total += 1
            best = max(best, cur)
        else:
            cur = 0
    return best, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3, help="how many button events to capture")
    ap.add_argument("--window", type=float, default=25.0, help="seconds to wait per event")
    ap.add_argument("--thresh", type=float, default=1.5, help="pin-1 falling trigger level (V)")
    ap.add_argument("--low", type=float, default=1.0, help="a sample below this counts as LOW")
    ap.add_argument("--cap-tb-us", type=float, default=5000.0, help="us/div (5000 = 50 ms window)")
    ap.add_argument("--trig-pin", type=int, default=1, choices=(1, 2, 3))
    ap.add_argument("--rail", type=float, default=3.0)
    ap.add_argument("--ilim", type=float, default=0.02)
    ap.add_argument("--ovp", type=float, default=3.6)
    args = ap.parse_args()

    trig_ch = PIN_CHANS[args.trig_pin]
    psu = PSU()
    awg = Awg(); print("AWG  :", awg.query("*IDN?"))
    scope = Scope(); print("SCOPE:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.8, offset=-2.0, coupling="DC")

    events = []
    try:
        psu.bring_up(args.rail, args.ilim, ovp=args.ovp)
        # Belt and braces: both AWG channels explicitly off, and verified quiet on the scope.
        awg.output(False, ch=1); awg.output(False, ch=2)
        time.sleep(0.6)
        scope.write(":TRIGger:SWEep AUTO"); scope.write(":RUN")
        scope.write(":TIMebase:MAIN:SCALe 0.0005")
        time.sleep(0.8)
        quiet = {p: scope.measure_item(PIN_CHANS[p], "VPP") for p in (1, 2, 3)}
        print("\n[quiet check, AWG off] " +
              "  ".join(f"pin{p} VPP={v:.2f}" for p, v in quiet.items()))
        if max(quiet.values()) > 0.5:
            print("  !! a pin is still swinging with the AWG off — something is driving the rig.")

        os.makedirs(OUTDIR, exist_ok=True)
        os.makedirs(FINDINGS, exist_ok=True)
        for rep in range(1, args.reps + 1):
            scope.arm_single(trig_ch=trig_ch, level=args.thresh, slope="NEGative",
                             mdepth=10_000, tb_scale=args.cap_tb_us / 1e6, sweep="NORMal")
            print(f"\n--- event {rep}/{args.reps} --- PRESS THE DATA BUTTON "
                  f"(up to {args.window:.0f}s)...", flush=True)
            if scope.wait_stop(timeout=args.window) != "STOP":
                print("    no trigger in the window.")
                events.append(None)
                continue
            time.sleep(0.5)
            tag = f"btnonly_{rep}"
            ev = {}
            for c in (1, 2, 3):
                pre, raw = scope.read_screen(c)
                with open(f"{OUTDIR}/{tag}_ch{c}.bin", "wb") as f: f.write(raw)
                with open(f"{OUTDIR}/{tag}_ch{c}.pre", "w") as f: f.write(pre)
                xinc, v = scale(pre, raw)
                longest, total = runs_below(v, args.low)
                ev[c] = {"xinc": xinc, "n": len(v), "min": min(v), "max": max(v),
                         "avg": sum(v) / len(v), "longest_low": longest, "total_low": total}
                ms = longest * xinc * 1e3
                print(f"    pin{c}: min {ev[c]['min']:+.2f}  max {ev[c]['max']:+.2f}  "
                      f"avg {ev[c]['avg']:+.2f}  longest-low {longest} samp ({ms:.2f} ms)  "
                      f"total-low {total}")
            scope.screenshot(f"{OUTDIR}/{tag}_scope.png")
            events.append(ev)
    finally:
        try:
            awg.output(False, ch=1); awg.output(False, ch=2)
        except Exception:
            pass
        psu.off(); awg.close(); scope.close()
        print("\nAWG + PSU OFF.")

    got = [e for e in events if e]
    print("\n==== VERDICT ====")
    if not got:
        print("  No pin-1 event captured with the button alone. That would RESTORE §11.15's")
        print("  'button + input edges are both required' — but note the threshold sweep's")
        print("  negative control DID fire, so re-run before trusting either result.")
        return

    xinc = got[0][trig_ch]["xinc"]
    glitchy = [e for e in got if e[trig_ch]["longest_low"] <= 2]
    real = [e for e in got if e[trig_ch]["longest_low"] > 10]
    print(f"  captured {len(got)}/{args.reps} events at {xinc*1e6:.1f} us/sample")
    if real:
        ms = [e[trig_ch]["longest_low"] * xinc * 1e3 for e in real]
        print(f"  *** {len(real)} REAL strobe(s): pin {args.trig_pin} held low for "
              f"{min(ms):.1f}-{max(ms):.1f} ms. ***")
        print("  => the DATA BUTTON ALONE triggers the response. No clock, no input edges.")
        print("  This CONTRADICTS §11.15 ('both required') and confirms review.md §1.3: the")
        print("  §11.12 button-alone negative was another false negative from the VMIN polling")
        print("  loop. The bench log needs correcting.")
    if glitchy:
        print(f"  {len(glitchy)} event(s) were 1-2 samples only = mechanical/EMI press glitch,")
        print("  not a strobe (the §11.8 artefact). Those prove nothing.")

    # The other half: with nothing driven, are pins 2/3 EVER pulled low?
    print("\n  --- pins 2/3, fully unmasked for the first time (no clock on either) ---")
    for p in (2, 3):
        lows = [e[PIN_CHANS[p]]["total_low"] for e in got]
        mins = [e[PIN_CHANS[p]]["min"] for e in got]
        print(f"    pin{p}: min {min(mins):+.2f} V, samples below {args.low} V per event: {lows}")
    if all(e[PIN_CHANS[p]]["total_low"] == 0 for e in got for p in (2, 3)):
        print("    Neither input is ever pulled low during the event -> the mic drives ONLY")
        print("    pin 1 on a button press. No CK+DATA pair, so nothing Digimatic-shaped here.")
    else:
        print("    *** An INPUT pin was pulled low during the event — the mic is driving more")
        print("    than pin 1. This is new; capture it at higher resolution next. ***")

    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = f"{FINDINGS}/button_only_{stamp}.txt"
    with open(path, "w") as f:
        f.write(f"button-alone capture (AWG OFF), pull-ups {args.rail:g} V\n{stamp}\n\n")
        f.write(f"quiet check (AWG off): {quiet}\n\n")
        for i, e in enumerate(events, 1):
            if not e:
                f.write(f"event {i}: no trigger\n")
                continue
            f.write(f"event {i}:\n")
            for c in (1, 2, 3):
                d = e[c]
                f.write(f"  pin{c}: min {d['min']:+.3f} max {d['max']:+.3f} avg {d['avg']:+.3f} "
                        f"longest_low {d['longest_low']} ({d['longest_low']*d['xinc']*1e3:.2f} ms) "
                        f"total_low {d['total_low']}\n")
    print(f"\nsaved -> {path}")


if __name__ == "__main__":
    main()
