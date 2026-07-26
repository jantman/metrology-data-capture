"""Clock-injection bring-up for the iGaging 35-065-U01 micrometer (see ARCHIVE/BRINGUP_PLAN.md).

The mic is host-clocked and silent until an external clock is driven into its CLK pin.
This script drives a square-wave clock from the DG902 Pro AWG into ONE candidate pin
(the physical AWG lead is on that pin), captures ALL FOUR connector-signal channels on the
DHO814 in one shot, and reports per-channel edge activity so you can tell CLK from DATA.

Channel map (fixed wiring — only the single AWG lead moves between runs):
    CH1 -> connector pin 1        CH3 -> connector pin 3
    CH2 -> connector pin 2        CH4 -> AWG output monitor (commanded clock)
Scope + AWG grounds -> connector pin 4 (== pin 5 == battery negative).

Per run you tell it which pin the AWG is physically driving (--drive-pin, 1|2|3). That
channel is the clock; the OTHER two pin-channels are watched for a data response. The script
ramps amplitude 1.5 -> 3.0 V (never above the 3 V battery ceiling) and stops as soon as a
non-driven channel shows clock-synchronous activity.

SAFETY (also enforced in scpi_lib.Awg): AWG through a ~1-2.2 kOhm series resistor, output
set High-Z. Never command a HIGH level above --max-volts (default 3.0).

Usage:
    python clock_injection.py --drive-pin 1
    python clock_injection.py --drive-pin 2 --all-levels
    python clock_injection.py --drive-pin 3 --freq 9000 --amplitudes 1.5,2.0,2.7,3.0

Outputs (per amplitude that gets captured), into ./captures/:
    inj_p<DRIVE>_<AMP>v_ch{1..4}.bin   raw BYTE memory
    inj_p<DRIVE>_<AMP>v_ch{1..4}.pre   waveform preamble (scaling)
    inj_p<DRIVE>_<AMP>v_scope.png      screenshot
Then run:  python analyze_capture.py captures/inj_p<DRIVE>_<AMP>v
"""
import argparse
import os
import time

from scpi_lib import Scope, Awg

OUTDIR = "captures"
DEFAULT_AMPS = [1.5, 1.8, 2.2, 2.7, 3.0]
PIN_CHANS = {1: 1, 2: 2, 3: 3}  # connector pin -> scope channel


def digitize_transitions(pre, data, thresh_frac=0.5):
    """Count logic transitions in a raw BYTE channel. Returns (transitions, vpp)."""
    parts = pre.split(",")
    yinc, yorig, yref = float(parts[7]), float(parts[8]), float(parts[9])
    vals = [(b - yorig - yref) * yinc for b in data]
    if not vals:
        return 0, 0.0
    lo, hi = min(vals), max(vals)
    vpp = hi - lo
    if vpp < 0.2:  # essentially flat / floating line, no real logic swing
        return 0, vpp
    thr_hi = lo + vpp * (thresh_frac + 0.1)
    thr_lo = lo + vpp * (thresh_frac - 0.1)
    state = None
    trans = 0
    for v in vals:
        if v > thr_hi and state != 1:
            if state is not None:
                trans += 1
            state = 1
        elif v < thr_lo and state != 0:
            if state is not None:
                trans += 1
            state = 0
    return trans, vpp


def capture_at(scope, awg, drive_pin, amp, freq, tag):
    """Set AWG amplitude, single-shot 4-channel capture, save, and return a report dict."""
    drive_ch = PIN_CHANS[drive_pin]
    awg.set_high_level(amp)
    time.sleep(0.2)

    # Trigger on the driven (clock) channel; a moderate level within the 0..amp swing.
    scope.arm_single(trig_ch=drive_ch, level=amp * 0.5, slope="POSitive",
                     mdepth=1_000_000, tb_scale=0.005)  # 50 ms window @ ~20 MSa/s
    status = scope.wait_stop(timeout=15)

    os.makedirs(OUTDIR, exist_ok=True)
    report = {"amp": amp, "status": status, "channels": {}}
    for ch in (1, 2, 3, 4):
        pre, raw = scope.read_raw(ch)
        with open(f"{OUTDIR}/{tag}_ch{ch}.bin", "wb") as f:
            f.write(raw)
        with open(f"{OUTDIR}/{tag}_ch{ch}.pre", "w") as f:
            f.write(pre)
        trans, vpp = digitize_transitions(pre, raw)
        report["channels"][ch] = {"transitions": trans, "vpp": round(vpp, 3)}
    scope.screenshot(f"{OUTDIR}/{tag}_scope.png")
    return report


def responded(report, drive_pin, min_trans=10, min_vpp=0.3):
    """True if a non-driven pin-channel shows a real logic swing with activity."""
    drive_ch = PIN_CHANS[drive_pin]
    for pin, ch in PIN_CHANS.items():
        if ch == drive_ch:
            continue
        c = report["channels"][ch]
        if c["transitions"] >= min_trans and c["vpp"] >= min_vpp:
            return pin
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--drive-pin", type=int, required=True, choices=(1, 2, 3),
                    help="connector pin the AWG lead is physically driving")
    ap.add_argument("--freq", type=float, default=9000, help="clock frequency Hz (default 9k)")
    ap.add_argument("--amplitudes", type=str, default=None,
                    help="comma list of HIGH levels V (default 1.5,1.8,2.2,2.7,3.0)")
    ap.add_argument("--max-volts", type=float, default=3.0, help="hard ceiling, never exceed")
    ap.add_argument("--all-levels", action="store_true",
                    help="capture every amplitude even after a response is seen")
    ap.add_argument("--duty", type=float, default=50)
    args = ap.parse_args()

    amps = ([float(x) for x in args.amplitudes.split(",")]
            if args.amplitudes else list(DEFAULT_AMPS))
    if any(a > args.max_volts for a in amps):
        raise SystemExit(f"amplitude exceeds --max-volts {args.max_volts}; refusing")

    awg = Awg()
    print("AWG IDN:", awg.query("*IDN?"))
    scope = Scope()
    print("SCOPE IDN:", scope.query("*IDN?"))

    # Configure scope channels: DC, ~0.5 V/div, offset to center a 0..3 V swing.
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.5, offset=-1.5, coupling="DC")

    # Configure (disabled) clock, then enable at the first amplitude.
    awg.square(freq=args.freq, low=0.0, high=amps[0], duty=args.duty)
    awg.output(True)
    print(f"AWG clock ON: {args.freq} Hz square, High-Z, driving connector pin {args.drive_pin}")

    try:
        found = None
        for amp in amps:
            tag = f"inj_p{args.drive_pin}_{amp:g}v"
            print(f"\n--- {amp:g} V ---")
            rep = capture_at(scope, awg, args.drive_pin, amp, args.freq, tag)
            print(f"  trigger status: {rep['status']}")
            for ch in (1, 2, 3, 4):
                c = rep["channels"][ch]
                pin = {1: "pin1", 2: "pin2", 3: "pin3", 4: "AWGmon"}[ch]
                mark = " <-DRIVEN" if ch == PIN_CHANS[args.drive_pin] else ""
                print(f"  CH{ch} ({pin}): {c['transitions']:>5} transitions, "
                      f"vpp={c['vpp']}V{mark}")
            hit = responded(rep, args.drive_pin)
            if hit:
                found = (amp, hit)
                print(f"  >>> RESPONSE on connector pin {hit} at {amp:g} V "
                      f"=> DRIVEN pin {args.drive_pin} looks like CLK, pin {hit} like DATA")
                if not args.all_levels:
                    break
        print("\n==== SUMMARY ====")
        if found:
            amp, pin = found
            print(f"CLK candidate = pin {args.drive_pin}; DATA candidate = pin {pin}; "
                  f"logic swing seen at {amp:g} V.")
            print(f"Next: python analyze_capture.py "
                  f"captures/inj_p{args.drive_pin}_{amp:g}v --clk-pin {args.drive_pin} "
                  f"--data-pin {pin}")
        else:
            print(f"No response while driving pin {args.drive_pin}. Move the AWG lead to the "
                  f"next candidate pin and rerun with --drive-pin.")
    finally:
        awg.output(False)  # leave the bench safe
        print("\nAWG output OFF.")
        awg.close()
        scope.close()


if __name__ == "__main__":
    main()
