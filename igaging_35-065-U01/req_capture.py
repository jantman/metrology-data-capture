"""REQ-triggered SPC read (Mitutoyo Digimatic-style) — assert REQ, let the DEVICE clock out.

Hypothesis (2026-07-26): this mic speaks Mitutoyo-compatible Digimatic SPC on its Micro-USB port.
The official 100-700-USB-MC adapter shares its SPC control box + 10-pin header with the SPC
100-700-USB (whose cable is a Mitutoyo-style "Type C" Digimatic SPC cable); only the connector/
cable differs. Digimatic is REQUEST-triggered and DEVICE-clocked: the reader holds pull-ups on
DATA/CK/REQ and pulls REQ LOW; the device then generates BOTH clock and data (~52 bits, 13 BCD
nibbles). Every prior test assumed host-clocked and injected OUR clock (wrong direction) and never
asserted REQ, so the device never transmitted -- exactly why every pin stayed silent.

This drives one pin (--req-pin) active-LOW at ~--freq Hz (pull-ups on all three signal pins) and
watches the other two for the DEVICE pulling them low (its CK + DATA). --capture arms a
falling-edge trigger on a watched pin to grab the actual device-clocked frame.

Wiring: PSU +3 V -> 10k -> each of pins 1/2/3; AWG CH1 -> 1k -> the REQ pin; PSU- and all grounds
-> pin 4; scope CH1/2/3 on pins 1/2/3, CH4 on AWG CH1 out.

    python req_capture.py --req-pin 2                 # try pin 2 as REQ, watch 1 & 3
    python req_capture.py --req-pin 2 --capture --trig-pin 3
"""
import argparse
import os
import time

from scpi_lib import Scope, Awg
from psu_lib import PSU
from clock_injection import digitize_transitions, PIN_CHANS, OUTDIR


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--req-pin", type=int, default=2, choices=(1, 2, 3))
    ap.add_argument("--freq", type=float, default=20.0, help="REQ assert rate (Hz)")
    ap.add_argument("--amp", type=float, default=3.0, help="REQ high level (V); idles high, pulses low")
    ap.add_argument("--secs", type=float, default=20.0)
    ap.add_argument("--rail", type=float, default=3.0)
    ap.add_argument("--ilim", type=float, default=0.02)
    ap.add_argument("--ovp", type=float, default=3.6)
    ap.add_argument("--thresh", type=float, default=1.5,
                    help="a watched pin dipping below this = the DEVICE is driving it")
    ap.add_argument("--capture", action="store_true",
                    help="arm a falling-edge trigger on --trig-pin to grab the device frame")
    ap.add_argument("--trig-pin", type=int, default=0, choices=(0, 1, 2, 3))
    ap.add_argument("--max-volts", type=float, default=3.0)
    args = ap.parse_args()
    if args.amp > args.max_volts:
        raise SystemExit("amp exceeds --max-volts")

    watch = [p for p in (1, 2, 3) if p != args.req_pin]
    psu = PSU()
    awg = Awg(); print("AWG:", awg.query("*IDN?"))
    scope = Scope(); print("SCOPE:", scope.query("*IDN?"))
    for ch in (1, 2, 3, 4):
        scope.setup_channel(ch, scale=0.8, offset=-2.0, coupling="DC")

    floor = {p: 9.0 for p in watch}
    try:
        psu.bring_up(args.rail, args.ilim, ovp=args.ovp)
        # REQ idles HIGH (matches the pull-up) and pulses LOW at --freq (active-low request).
        awg.square(args.freq, low=0.0, high=args.amp, ch=1)
        awg.output(True, ch=1); time.sleep(0.3)
        print(f"\nREQ on pin {args.req_pin}: {args.freq:g} Hz active-low pulses; "
              f"watching pins {watch} pulled to {args.rail:g} V.")
        os.makedirs(OUTDIR, exist_ok=True)

        if args.capture and args.trig_pin:
            tch = PIN_CHANS[args.trig_pin]
            print(f"\n>>> Armed: trigger on pin {args.trig_pin} falling through {args.thresh} V "
                  f"(device CK/DATA). Waiting up to {args.secs:.0f}s... <<<")
            scope.arm_single(trig_ch=tch, level=args.thresh, slope="NEGative",
                             mdepth=1_000_000, tb_scale=0.002, sweep="NORMal")
            status = scope.wait_stop(timeout=args.secs)
            if status == "STOP":
                tag = f"req_p{args.req_pin}_frame"
                for c in (1, 2, 3, 4):
                    pre, raw = scope.read_raw(c)
                    with open(f"{OUTDIR}/{tag}_ch{c}.bin", "wb") as f: f.write(raw)
                    with open(f"{OUTDIR}/{tag}_ch{c}.pre", "w") as f: f.write(pre)
                    t, v = digitize_transitions(pre, raw)
                    print(f"  ch{c}: {t} transitions, vpp={v:.2f}")
                scope.screenshot(f"{OUTDIR}/{tag}_scope.png")
                print(f"\n*** CAPTURED a device-driven frame after REQ on pin {args.req_pin}! "
                      f"Digimatic-style SPC confirmed. Analyze: python analyze_capture.py "
                      f"{OUTDIR}/{tag} ***")
            else:
                print(f"\nNo device edge on pin {args.trig_pin} in {args.secs:.0f}s (status {status}).")
            return

        # Monitor: watch both non-REQ pins for the device pulling them low.
        scope.write(":TRIGger:SWEep AUTO"); scope.write(":RUN")
        scope.write(":TIMebase:MAIN:SCALe 0.005")  # 50 ms window (a REQ cycle + response)
        time.sleep(0.8)
        n = 0
        t0 = time.time()
        while time.time() - t0 < args.secs:
            dip = False
            for p in watch:
                v = scope.measure_item(PIN_CHANS[p], "VMIN")
                floor[p] = min(floor[p], v)
                if v < args.thresh:
                    dip = True
            n += 1
            if dip or n % 8 == 0:
                print(f"  t={time.time()-t0:5.1f}s  " + " ".join(
                    f"pin{p} VMIN={scope.measure_item(PIN_CHANS[p],'VMIN'):+.2f}" for p in watch) +
                    ("   <== DIP (device driving!)" if dip else ""))
        scope.screenshot(f"{OUTDIR}/req_p{args.req_pin}_scope.png")
    finally:
        awg.output(False, ch=1); psu.off(); awg.close(); scope.close()
        print("AWG + PSU OFF.")

    print("\n==== RESULT ====")
    for p in watch:
        print(f"  pin{p}: lowest VMIN {floor[p]:+.2f} V")
    active = [p for p in watch if floor[p] < args.thresh]
    if active:
        print(f"*** With REQ on pin {args.req_pin}, the DEVICE pulled pin(s) {active} LOW -> "
              f"Digimatic-style SPC response! ***")
        print(f"Grab the frame: python req_capture.py --req-pin {args.req_pin} --capture "
              f"--trig-pin {active[0]}")
    else:
        print(f"No device response with REQ on pin {args.req_pin}. Try --req-pin = a different "
              f"pin, or a slower --freq (e.g. 5-10 Hz to give the device more time low).")


if __name__ == "__main__":
    main()
