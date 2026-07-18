"""Passive self-clocked-frame probe (see BRINGUP_PLAN.md Phase A, button hypothesis).

Tests whether pressing the mic's DATA button emits a SINGLE self-clocked frame — i.e. the
mic drives BOTH clock and data itself for one frame, with NO external clock (the Mitutoyo/SPC
"send on button press" behavior that the user's other calipers exhibit).

§11.4 tried this once with a blind single-shot edge trigger and caught nothing, but this does
it properly:
  - AWG output is forced OFF (no injection at all).
  - Scope armed NORMAL sweep (won't auto-trigger — it WAITS for a real edge), sensitive level,
    on a chosen pin, with a long timeout so you can press the button several times.
  - A wide window (default 40 ms) fully contains a ~2.3 ms 21-bit frame at ~9 kHz with margin.
If the mic self-clocks a frame, the scope triggers on it and we capture all pins at once,
revealing self-generated CLK+DATA (which pins move together => those are CLK/DATA).

    python passive_capture.py --trig-pin 1                 # then press DATA a few times
    python passive_capture.py --trig-pin 2 --edge falling  # idle-high output? try falling
    python passive_capture.py --trig-pin 3 --level 0.25 --timeout 30

If it triggers, feed the saved prefix to analyze_capture.py to look for frame structure.
"""
import argparse

from scpi_lib import Scope, Awg
from clock_injection import digitize_transitions, OUTDIR
import os

PIN_CHANS = {1: 1, 2: 2, 3: 3}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trig-pin", type=int, required=True, choices=(1, 2, 3),
                    help="pin to trigger on (any moving line will do if the mic self-clocks)")
    ap.add_argument("--edge", choices=("rising", "falling"), default="rising",
                    help="idle floats near 0 V, so a self-clocked pulse rises -> default rising")
    ap.add_argument("--level", type=float, default=0.4, help="trigger level V (above noise)")
    ap.add_argument("--window-ms", type=float, default=40.0, help="capture window (ms)")
    ap.add_argument("--timeout", type=float, default=25.0, help="seconds to wait for a press")
    args = ap.parse_args()

    # Force the AWG OFF — this is a purely passive test.
    try:
        awg = Awg(); awg.output(False); awg.close()
    except Exception as e:
        print(f"(warning: could not confirm AWG off: {e})")

    scope = Scope(); print("SCOPE IDN:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.5, offset=-1.5, coupling="DC")

    slope = "POSitive" if args.edge == "rising" else "NEGative"
    tb = args.window_ms / 1000.0 / 10.0  # 10 divisions
    scope.arm_single(trig_ch=PIN_CHANS[args.trig_pin], level=args.level, slope=slope,
                     mdepth=1_000_000, tb_scale=tb)
    print(f"\nAWG OFF. Scope armed NORMAL sweep on pin {args.trig_pin}, {args.edge} @ "
          f"{args.level} V, {args.window_ms:g} ms window.")
    print(f">>> PRESS the mic's DATA button now — several times over ~{args.timeout:g} s.\n")

    status = scope.wait_stop(timeout=args.timeout)
    if status != "STOP":
        print(f"No trigger (status={status}). Nothing self-clocked crossed {args.level} V on "
              f"pin {args.trig_pin}. Try another --trig-pin / --edge / lower --level.")
        scope.close()
        return

    os.makedirs(OUTDIR, exist_ok=True)
    tag = f"passive_trig{args.trig_pin}_{args.edge}"
    print(f"TRIGGERED — capturing. Saving {OUTDIR}/{tag}_ch*.\n")
    for ch in (1, 2, 3, 4):
        pre, raw = scope.read_raw(ch)
        with open(f"{OUTDIR}/{tag}_ch{ch}.bin", "wb") as f: f.write(raw)
        with open(f"{OUTDIR}/{tag}_ch{ch}.pre", "w") as f: f.write(pre)
        trans, vpp = digitize_transitions(pre, raw)
        name = {1: "pin1", 2: "pin2", 3: "pin3", 4: "CH4"}[ch]
        mark = " <-TRIG" if ch == PIN_CHANS[args.trig_pin] else ""
        note = "  (activity!)" if trans >= 10 and vpp >= 0.4 else ""
        print(f"  CH{ch} ({name}): {trans:>5} transitions, vpp={vpp:.3f}V{mark}{note}")
    scope.screenshot(f"{OUTDIR}/{tag}_scope.png")
    print(f"\nIf two pins show many transitions, the mic SELF-CLOCKED a frame -> those are "
          f"CLK+DATA. Analyze: python analyze_capture.py {OUTDIR}/{tag}")
    scope.close()


if __name__ == "__main__":
    main()
