"""Two-input handshake: drive BOTH inputs (CLK + held REQ) + DATA button, watch pin 1 for bits.

Pin roles (§11.15): pin 1 = mic OUTPUT, pin 2/pin 3 = INPUTS. Driving ONE input + the button makes
pin 1 strobe low but not shift data. A real reader almost certainly drives BOTH inputs — one CLK,
one REQ/gate. This drives AWG CH1 = CLK (square) on --clk-pin and AWG CH2 = REQ (DC hold, default
0 V = asserted low) on --req-pin, and captures pin 1 (--data-pin) on its falling edge to see whether
it TOGGLES many times (shifting bits = DATA) instead of a single strobe.

Wiring: PSU +3 V -> 10k -> each of pins 1/2/3; AWG CH1 -> 1k -> clk-pin; AWG CH2 -> 1k -> req-pin;
scope CH1/2/3 on pins 1/2/3, CH4 on AWG CH1 out; PSU- and all grounds -> pin 4.

    python two_input_capture.py --clk-pin 2 --req-pin 3               # CLK pin2, REQ(low) pin3
    python two_input_capture.py --clk-pin 2 --req-pin 3 --req-volts 3 # REQ held HIGH instead
    python two_input_capture.py --clk-pin 3 --req-pin 2               # swap roles
"""
import argparse
import os
import time

from scpi_lib import Scope, Awg
from psu_lib import PSU
from clock_injection import digitize_transitions, PIN_CHANS, OUTDIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clk-pin", type=int, default=2, choices=(1, 2, 3))
    ap.add_argument("--req-pin", type=int, default=3, choices=(1, 2, 3))
    ap.add_argument("--data-pin", type=int, default=1, choices=(1, 2, 3))
    ap.add_argument("--freq", type=float, default=2000)
    ap.add_argument("--amp", type=float, default=3.0)
    ap.add_argument("--req-volts", type=float, default=0.0,
                    help="DC level held on the REQ pin (0 = assert low, 3 = high)")
    ap.add_argument("--cap-tb-us", type=float, default=2000.0, help="capture window: us/div")
    ap.add_argument("--secs", type=float, default=30.0)
    ap.add_argument("--thresh", type=float, default=1.5)
    ap.add_argument("--rail", type=float, default=3.0)
    ap.add_argument("--ilim", type=float, default=0.02)
    ap.add_argument("--ovp", type=float, default=3.6)
    ap.add_argument("--max-volts", type=float, default=3.0)
    args = ap.parse_args()
    if args.amp > args.max_volts or args.req_volts > args.max_volts:
        raise SystemExit("amp/req-volts exceeds --max-volts")
    if len({args.clk_pin, args.req_pin, args.data_pin}) != 3:
        raise SystemExit("clk/req/data pins must be distinct")

    data_ch = PIN_CHANS[args.data_pin]
    psu = PSU()
    awg = Awg(); print("AWG:", awg.query("*IDN?"))
    scope = Scope(); print("SCOPE:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.8, offset=-2.0, coupling="DC")

    status = None
    vals = {}
    try:
        psu.bring_up(args.rail, args.ilim, ovp=args.ovp)
        awg.dc(args.req_volts, ch=2); awg.output(True, ch=2)          # CH2 = REQ (held)
        awg.square(args.freq, low=0.0, high=args.amp, ch=1); awg.output(True, ch=1)  # CH1 = CLK
        time.sleep(0.4)
        print(f"\nCLK {args.freq:g} Hz on pin {args.clk_pin} (CH1); REQ held {args.req_volts:g} V "
              f"on pin {args.req_pin} (CH2); watching DATA pin {args.data_pin}.")
        os.makedirs(OUTDIR, exist_ok=True)
        print(f"\n>>> PRESS THE DATA BUTTON repeatedly for ~{args.secs:.0f}s NOW. <<<")
        scope.arm_single(trig_ch=data_ch, level=args.thresh, slope="NEGative",
                         mdepth=1_000_000, tb_scale=args.cap_tb_us / 1e6, sweep="NORMal")
        status = scope.wait_stop(timeout=args.secs)
        if status == "STOP":
            time.sleep(0.5)
            tag = f"twoin_clk{args.clk_pin}_req{args.req_pin}"
            for c in (1, 2, 3, 4):
                pre, raw = scope.read_screen(c)
                with open(f"{OUTDIR}/{tag}_ch{c}.bin", "wb") as f: f.write(raw)
                with open(f"{OUTDIR}/{tag}_ch{c}.pre", "w") as f: f.write(pre)
                t, v = digitize_transitions(pre, raw)
                vals[c] = (t, v)
                print(f"  ch{c}: {t} transitions, vpp={v:.2f}, bytes {min(raw)}..{max(raw)}")
            scope.screenshot(f"{OUTDIR}/{tag}_scope.png")
        else:
            print(f"\nNo pin {args.data_pin} falling edge in {args.secs:.0f}s (status {status}).")
    finally:
        awg.output(False, ch=1); awg.output(False, ch=2)
        psu.off(); awg.close(); scope.close()
        print("AWG + PSU OFF.")

    if status == "STOP":
        dt = vals[data_ch][0]
        print("\n==== RESULT ====")
        if dt > 3:
            print(f"*** DATA pin {args.data_pin} TOGGLED {dt}x after trigger -> SHIFTING BITS! "
                  f"Analyze: python analyze_capture.py {OUTDIR}/{tag} "
                  f"--clk-pin {args.clk_pin} --data-pin {args.data_pin} ***")
        else:
            print(f"pin {args.data_pin}: only {dt} transitions -> still a strobe, no shift with "
                  f"CLK=pin{args.clk_pin} / REQ=pin{args.req_pin}@{args.req_volts:g}V. Next: "
                  f"--req-volts 3, swap --clk-pin/--req-pin, or a slower --freq.")


if __name__ == "__main__":
    main()
