"""The properly-instrumented search for the mic's data output. Unattended.

WHY THIS IS DIFFERENT FROM EVERY PRIOR CLOCKING TEST. §11.19 established that pin 1 is the DATA
button's switch contact, so the real interface is just pins 2 and 3, and the mic has never been
observed to drive anything. But the negatives behind that are weaker than they look:

  * §11.12 Test 2 detected with the VMIN polling loop covering ~4-12%% of wall-clock time — the
    defect behind three separate false negatives (review.md §1.3).
  * §11.16's armed captures triggered on **pin 1**, i.e. on the button, not on a data pin.

**No test has ever armed a trigger on a data pin during a clocked read.** That is the gap this
closes: a continuously-armed falling-edge trigger sits on pin 3 for the whole dwell, so a single
brief pull-low anywhere in the window is caught.

WIRING (as built 2026-07-26):
    PSU +3 V -> 10k -> each of pins 1/2/3
    AWG CH1  -> 1k  -> pin 1     simulated DATA button: LOW = held, HIGH = released
    AWG CH2  -> 1k  -> pin 2     the clock
    scope CH1/2/3 on pins 1/2/3, CH4 on AWG CH1 out; grounds to pin 4(+5)
    Mic AWAKE, battery IN, case closed. DO NOT press the physical button during the run.

WHAT IT SWEEPS. Button held vs released x clock rate x duty x continuous/burst. The 20 % duty of
the reference implementation has never once been delivered (review.md §5.5a); nor has burst framing
on an input pin with pull-ups (§5.5).

SELF-VALIDATING. It first proves the detection path works by pulsing pin 1 low with CH1 and
confirming an armed trigger on pin 1 fires. If that control fails, nothing downstream would mean
anything, so it stops. Every combination also verifies the clock is really present on pin 2 before
arming, so a dead lead cannot masquerade as "no response".

    python interface_sweep.py                    # full sweep, ~5 min, unattended
    python interface_sweep.py --dwell 15         # longer dwell per combination
"""
import argparse
import datetime
import itertools
import os
import time

from scpi_lib import Scope, Awg
from psu_lib import PSU
from clock_injection import PIN_CHANS, OUTDIR

FINDINGS = "findings"
_log = None


def log(msg=""):
    print(msg, flush=True)
    if _log:
        _log.write(msg + "\n"); _log.flush(); os.fsync(_log.fileno())


def scale(pre, raw):
    p = pre.split(",")
    yinc, yorig, yref = float(p[7]), float(p[8]), float(p[9])
    return float(p[4]), [(b - yorig - yref) * yinc for b in raw]


def longest_low(vals, thresh):
    best = cur = 0
    for v in vals:
        cur = cur + 1 if v < thresh else 0
        best = max(best, cur)
    return best


def main():
    global _log
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-pin", type=int, default=3, choices=(1, 2, 3),
                    help="pin watched for the mic pulling it low")
    ap.add_argument("--clk-pin", type=int, default=2, choices=(1, 2, 3))
    ap.add_argument("--btn-pin", type=int, default=1, choices=(1, 2, 3))
    ap.add_argument("--freqs", default="9000,2000,500,100")
    ap.add_argument("--duties", default="50,20")
    ap.add_argument("--modes", default="continuous,burst")
    ap.add_argument("--buttons", default="held,released")
    ap.add_argument("--dwell", type=float, default=8.0, help="seconds armed per combination")
    ap.add_argument("--amp", type=float, default=3.0)
    ap.add_argument("--thresh", type=float, default=1.5, help="data-pin falling trigger level")
    ap.add_argument("--ncycles", type=int, default=21)
    ap.add_argument("--gap-ms", type=float, default=7.0,
                    help="IDLE GAP after each burst. The burst PERIOD is computed as "
                         "ncycles/freq + gap, never a fixed value: at 2 kHz a 21-cycle burst is "
                         "already 10.5 ms long, so a fixed 10 ms period makes it run continuously "
                         "and the burst axis silently tests nothing.")
    ap.add_argument("--rail", type=float, default=3.0)
    ap.add_argument("--ilim", type=float, default=0.02)
    ap.add_argument("--ovp", type=float, default=3.6)
    ap.add_argument("--max-volts", type=float, default=3.0)
    args = ap.parse_args()
    if args.amp > args.max_volts:
        raise SystemExit("amp exceeds --max-volts")

    freqs = [float(x) for x in args.freqs.split(",")]
    duties = [float(x) for x in args.duties.split(",")]
    modes = args.modes.split(",")
    buttons = args.buttons.split(",")
    data_ch, clk_ch, btn_ch = (PIN_CHANS[args.data_pin], PIN_CHANS[args.clk_pin],
                               PIN_CHANS[args.btn_pin])

    os.makedirs(FINDINGS, exist_ok=True); os.makedirs(OUTDIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    _log = open(f"{FINDINGS}/interface_sweep_{stamp}.txt", "w")

    psu = PSU()
    awg = Awg(); log(f"AWG  : {awg.query('*IDN?')}")
    scope = Scope(); log(f"SCOPE: {scope.query('*IDN?')}")

    # Record the run parameters IN THE LOG. Without this the archived file cannot be told apart
    # from any other run — the §11.22 logs differ only by rail voltage, which was recoverable
    # solely by inference from the clkVPP column. Note psu_lib prints its bring-up line to stdout
    # only, so the rail has to be logged here explicitly.
    log(f"\nRUN {stamp}")
    log(f"  clk pin {args.clk_pin} | data pin {args.data_pin} (watched) | button pin {args.btn_pin}")
    log(f"  rail {args.rail:g} V | amp {args.amp:g} V | trigger {args.thresh:g} V falling")
    log(f"  freqs {args.freqs} Hz | duties {args.duties} % | modes {args.modes} | "
        f"buttons {args.buttons}")
    log(f"  burst {args.ncycles} cycles + {args.gap_ms:g} ms gap | dwell {args.dwell:g} s")
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.8, offset=-2.0, coupling="DC")

    hits = []
    combos = list(itertools.product(buttons, modes, freqs, duties))
    try:
        psu.bring_up(args.rail, args.ilim, ovp=args.ovp)
        awg.output(False, ch=1); awg.output(False, ch=2)
        time.sleep(0.5)

        # ---- positive control: prove the arm/trigger/capture path works at all ----------
        log("\n[control] pulsing pin 1 LOW via CH1; an armed trigger on pin 1 must fire.")
        awg.dc(0.0, ch=1)
        scope.arm_single(trig_ch=btn_ch, level=args.thresh, slope="NEGative",
                         mdepth=10_000, tb_scale=0.005, sweep="NORMal")
        time.sleep(0.3)
        awg.output(True, ch=1)               # release->held transition = falling edge
        ok = scope.wait_stop(timeout=8.0) == "STOP"
        log(f"[control] trigger {'FIRED — detection path good' if ok else 'DID NOT FIRE'}")
        if not ok:
            log("[control] *** The detection path is not working (CH1 lead on pin 1? trigger")
            log("          level? scope channel map?). Everything below would be meaningless.")
            return
        awg.output(False, ch=1)

        # ---- the sweep -----------------------------------------------------------------
        log(f"\nSweeping {len(combos)} combinations, {args.dwell:.0f}s each "
            f"(~{len(combos)*(args.dwell+4)/60:.0f} min). Watching pin {args.data_pin} for a "
            f"falling edge through {args.thresh} V.\n")
        log(f"{'button':9} {'mode':11} {'freq':>7} {'duty':>5}  {'clkVPP':>7}  result")
        log("-" * 62)

        for button, mode, freq, duty in combos:
            # simulated button on pin 1
            awg.dc(0.0 if button == "held" else args.rail, ch=1)
            awg.output(True, ch=1)
            # clock on pin 2
            if mode == "burst":
                # NB: do NOT call burst_capture.configure_burst() here — it targets CH1, which is
                # now the simulated BUTTON. Calling it would reconfigure CH1 from DC to a square
                # wave and silently destroy the button state. Configure CH2 directly instead.
                awg.set_highz(2)
                awg.write(":SOURce2:FUNCtion SQUare")
                awg.write(f":SOURce2:FREQuency {freq}")
                awg.write(":SOURce2:VOLTage:LOW 0")
                awg.write(f":SOURce2:VOLTage:HIGH {args.amp}")
                awg.write(f":SOURce2:FUNCtion:SQUare:DCYCle {duty}")
                awg.write(":SOURce2:BURSt:STATe ON")
                awg.write(":SOURce2:BURSt:MODE TRIGgered")
                awg.write(f":SOURce2:BURSt:NCYCles {args.ncycles}")
                burst_s = args.ncycles / freq
                period_s = burst_s + args.gap_ms / 1000.0
                awg.write(f":SOURce2:BURSt:INTernal:PERiod {period_s:g}")
                awg.write(":TRIGger2:SOURce IMMediate")
                awg.write(":SOURce1:BURSt:STATe OFF")
            else:
                awg.write(":SOURce2:BURSt:STATe OFF")
                awg.square(freq, low=0.0, high=args.amp, duty=duty, ch=2)
            awg.output(True, ch=2)
            time.sleep(0.5)

            # Clock-present guard. The window MUST span at least one whole burst period —
            # a short window lands in the idle gap most of the time and reports "no clock"
            # for a perfectly good burst train (the §11.8 trap).
            if mode == "burst":
                guard_tb = 2.0 * period_s / 10.0
            else:
                guard_tb = max(2e-5, 2.0 / freq / 10)
            scope.write(":TRIGger:SWEep AUTO"); scope.write(":RUN")
            scope.write(f":TIMebase:MAIN:SCALe {guard_tb:g}")
            time.sleep(0.8)
            clk_vpp = max(scope.measure_item(clk_ch, "VPP") for _ in range(3))
            if clk_vpp < 1.0:
                log(f"{button:9} {mode:11} {freq:7.0f} {duty:5.0f}  {clk_vpp:7.2f}  "
                    f"VOID (no clock on pin {args.clk_pin})")
                continue
            if mode == "burst":
                log(f"    (burst {burst_s*1e3:.2f} ms + {args.gap_ms:g} ms gap "
                    f"= {period_s*1e3:.2f} ms period)")

            scope.arm_single(trig_ch=data_ch, level=args.thresh, slope="NEGative",
                             mdepth=10_000, tb_scale=0.005, sweep="NORMal")
            fired = scope.wait_stop(timeout=args.dwell) == "STOP"
            if not fired:
                log(f"{button:9} {mode:11} {freq:7.0f} {duty:5.0f}  {clk_vpp:7.2f}  -")
                continue

            time.sleep(0.4)
            pre, raw = scope.read_screen(data_ch)
            xinc, v = scale(pre, raw)
            nlow = longest_low(v, 1.0)
            tag = f"iface_{button}_{mode}_{freq:.0f}_{duty:.0f}"
            for c in (1, 2, 3):
                p2, r2 = scope.read_screen(c)
                with open(f"{OUTDIR}/{tag}_ch{c}.bin", "wb") as f: f.write(r2)
                with open(f"{OUTDIR}/{tag}_ch{c}.pre", "w") as f: f.write(p2)
            scope.screenshot(f"{OUTDIR}/{tag}_scope.png")
            verdict = ("*** DRIVEN LOW ***" if nlow >= 3 else "glitch (1-2 samples)")
            log(f"{button:9} {mode:11} {freq:7.0f} {duty:5.0f}  {clk_vpp:7.2f}  "
                f"TRIGGERED  min={min(v):+.2f}V  longest-low={nlow} samp  {verdict}")
            if nlow >= 3:
                hits.append((button, mode, freq, duty, nlow, tag))
    finally:
        try:
            awg.write(":SOURce1:BURSt:STATe OFF"); awg.write(":SOURce2:BURSt:STATe OFF")
            awg.output(False, ch=1); awg.output(False, ch=2)
        except Exception:
            pass
        psu.off(); awg.close(); scope.close()
        # Stamp the END as well as the start. There is no rig-side awake detector (§11.23), so a
        # run's precondition can only be audited afterwards from its time window against the ~27
        # min auto-off — which needs both ends recorded, not just the start.
        log(f"\nAWG + PSU OFF.  finished {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")

    log("\n==== RESULT ====")
    if hits:
        log(f"  *** pin {args.data_pin} WAS DRIVEN LOW in {len(hits)} combination(s): ***")
        for b, m, f_, d, n, tag in hits:
            log(f"      button={b} {m} {f_:.0f} Hz {d:.0f}%  ({n} samples low)  -> captures/{tag}_*")
        log(f"\n  Analyse: python analyze_capture.py {OUTDIR}/{hits[0][5]} "
            f"--clk-pin {args.clk_pin} --data-pin {args.data_pin}")
    else:
        log(f"  pin {args.data_pin} was never pulled low, across all {len(combos)} combinations,")
        log("  with a continuously-armed trigger (not the polling loop that produced the earlier")
        log("  false negatives). This is the first trustworthy negative for the data interface.")
        log(f"\n  If the reverse assignment (--clk-pin {args.data_pin} --data-pin {args.clk_pin}),")
        log("  100k pull-ups and lower rail voltages have ALSO been tried, the matrix is complete")
        log("  and the mic does not respond to an open-loop clock — see BENCH_LOG §11.24, where")
        log("  all of that came back negative across 160 combinations. The cable sniff is then the")
        log("  way, and re-running this in another configuration adds nothing.")
    if _log:
        _log.close()


if __name__ == "__main__":
    main()
