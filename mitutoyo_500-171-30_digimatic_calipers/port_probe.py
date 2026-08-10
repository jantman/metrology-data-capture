"""STEP 1+2 of bring-up: identify the Digimatic pins, then answer the ONE question the
whole hardware design hangs on -- is the caliper's CK/DATA output a true open collector?

Why this matters (README "The open-drain question"): every hobby implementation on the web
wires CK/DATA straight to a 5 V or 3.3 V MCU input with a pull-up, which is only valid if the
tool's outputs are open collectors that go high-impedance when idle. But Mitutoyo's own logic
runs off a 1.55 V SR44 cell, and the published pinouts describe the tool-side signals as
"0-1.5 V". If the lines are instead DRIVEN to ~1.5 V (or clamped to the internal rail), then:

  * a 3.3 V pull-up is fighting the tool's clamp diode -- current injected into a 1.5 V rail;
  * an ESP32-S3 GPIO (VIH ~= 2.48 V) would read a stuck LOW and never see a single bit.

Those two cases need completely different front ends, and they are trivially distinguished by
measuring the idle voltage on the line with a known pull-up resistor fitted:

  pulled-up idle ~= 3.3 V  -> true open collector, high-Z when idle. Direct-to-GPIO wins.
  pulled-up idle ~= 1.5-2.2 V -> clamped to the tool's own rail. Level translation required.
  pulled-up idle ~= 0 V    -> line is asserted at idle (or the pin map is wrong). Stop, re-map.

The pull-up rail comes from the bench supply through 100 kOhm, so even the worst case injects
only (3.3-1.5)/100k = 18 uA into the caliper -- less than its own quiescent draw, and current-
limited at the supply as well. Nothing here can plausibly harm the instrument.

NOTHING IN THIS SCRIPT DRIVES A PIN. REQ is only ever observed, never asserted: the trigger is
the 959149's own DATA switch (that is the whole point of the passive-listen design).

RUN IT IN A REAL TERMINAL (it prompts between probe placements):

    cd mitutoyo_500-171-30_digimatic_calipers && python3 port_probe.py

Output is teed line by line to findings/port_probe_latest.txt (fixed path, written as we go so
an abort still leaves a log), with a timestamped archive copy on completion.

Networking to the bench instruments needs Bash `dangerouslyDisableSandbox`.
"""
import argparse
import datetime
import os
import shutil
import sys

from dmm_lib import DMM
from psu_lib import PSU

OUTDIR = "findings"
LOG_PATH = os.path.join(OUTDIR, "port_probe_latest.txt")

# Digimatic 10-pin assignment we are testing against (README "Pinout"). Pins 6-10 are
# unconnected on every published pinout; we sweep them anyway because a wrong assumption
# here is cheap to disprove and expensive to discover later.
PINS = {1: "GND", 2: "DATA", 3: "CK", 4: "RDY", 5: "REQ",
        6: "n/c", 7: "n/c", 8: "n/c", 9: "n/c", 10: "n/c"}

PULLUP_OHMS = 100_000
RAIL_V = 3.3


class Tee:
    def __init__(self, path):
        self.f = open(path, "w", buffering=1)

    def __call__(self, *parts):
        line = " ".join(str(p) for p in parts)
        print(line)
        self.f.write(line + "\n")


def prompt(say, text):
    say(f"\n>>> {text}")
    try:
        input("    press Enter when ready (Ctrl-C to abort) ... ")
    except (EOFError, KeyboardInterrupt):
        say("\n[abort] operator stopped the run")
        sys.exit(1)


def read_v(dmm, say, label):
    m = dmm.read_settled(expect_function="VOLT_DC")
    v = m["value"] if isinstance(m, dict) else m
    say(f"    {label:<28} {v:+.4f} V")
    return v


def phase_a(dmm, say):
    """Idle DC levels of every pin, referenced to the presumed GND, caliper powered."""
    say("\n" + "=" * 72)
    say("PHASE A -- idle levels, and confirm which pin is which")
    say("=" * 72)
    say("Caliper ON, 959149 plugged into the caliper and into the 2x5 receptacle.")
    say("DMM BLACK lead stays on receptacle pin 1 (presumed GND) for all of Phase A.")

    idle = {}
    for pin, name in PINS.items():
        if pin == 1:
            continue
        prompt(say, f"RED lead -> pin {pin} (expected: {name})")
        idle[pin] = read_v(dmm, say, f"pin {pin} ({name}) idle")

    say("\n  Interpretation:")
    say("    * a pin sitting at ~1.5 V is pulled up inside the tool to its SR44 rail")
    say("    * a pin sitting at ~0 V is either GND or actively held low")
    say("    * a floating pin reads as noise / drifts -- note it as UNSTABLE")
    say("    * pins 6-10 should be dead (open); anything alive there breaks the assumed pinout")
    return idle


def phase_b(dmm, say):
    """Press the cable's DATA switch and watch which pin goes low -> that pin is REQ.

    This is the one identification that needs no assumptions at all: the switch is wired to
    REQ, so whichever pin the button pulls to 0 V IS REQ, full stop. It also proves the
    switch works before we spend scope time waiting for a frame that never comes."""
    say("\n" + "=" * 72)
    say("PHASE B -- identify REQ by pressing the cable's DATA switch")
    say("=" * 72)
    held = {}
    for pin in (5, 4, 3, 2):
        prompt(say, f"RED lead -> pin {pin} ({PINS[pin]}), then HOLD the cable's DATA button "
                    f"down while the reading settles")
        held[pin] = read_v(dmm, say, f"pin {pin} with DATA held")
    say("\n  Expect exactly ONE pin (nominally pin 5) to sit at ~0 V while held. That is REQ.")
    say("  If a DIFFERENT pin goes low, the receptacle's pin numbering is mirrored or rotated")
    say("  relative to the assumed map -- fix the map in README before going further.")
    return held


def phase_c(psu, dmm, say, rail, rohm):
    """The open-drain determination: idle voltage on each output with a known pull-up."""
    say("\n" + "=" * 72)
    say(f"PHASE C -- open-collector test ({rohm/1000:.0f} kOhm pull-up to {rail:.2f} V)")
    say("=" * 72)
    say("Wire: PSU + --[{:.0f}k]-- signal pin ; PSU - -- receptacle pin 1 (GND).".format(rohm / 1000))
    say("Keep the DMM across the SIGNAL PIN and GND (i.e. measuring the pulled-up node).")

    psu.bring_up(rail, ilim=0.005, ovp=rail + 0.5)
    say(f"[psu] up at {rail:.2f} V, 5 mA limit")

    verdicts = {}
    try:
        for pin in (3, 2, 4):
            prompt(say, f"pull-up resistor -> pin {pin} ({PINS[pin]}); DMM across pin {pin} and GND")
            v = read_v(dmm, say, f"pin {pin} ({PINS[pin]}) pulled up")
            i_ua = (rail - v) / rohm * 1e6
            say(f"    -> current into the tool: {i_ua:.1f} uA")
            if v >= rail - 0.15:
                verdict = "OPEN COLLECTOR (high-Z at idle) -- direct-to-GPIO front end is valid"
            elif 1.2 <= v <= 2.4:
                verdict = ("CLAMPED to the tool's ~1.5 V rail -- a 3.3 V GPIO will NOT see a "
                           "valid high; use the level-translated front end")
            elif v <= 0.4:
                verdict = ("HELD LOW at idle -- either this pin is not an output, the pin map "
                           "is wrong, or the tool asserts it between frames")
            else:
                verdict = "AMBIGUOUS -- record it, and settle it on the scope in step 3"
            say(f"    -> VERDICT pin {pin}: {verdict}")
            verdicts[pin] = (v, verdict)

        prompt(say, "with the pull-up still fitted, check the caliper's LCD reads normally and "
                    "responds to moving the jaws")
        say("    (a disturbed reading here would mean the pull-up is loading the tool -- it "
            "should not, at 100 kOhm)")
    finally:
        psu.off()
        say("[psu] output off")
    return verdicts


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rail", type=float, default=RAIL_V, help="pull-up rail voltage")
    ap.add_argument("--rpullup", type=float, default=PULLUP_OHMS, help="pull-up resistor, ohms")
    ap.add_argument("--skip-a", action="store_true", help="skip the idle-level sweep")
    args = ap.parse_args()

    os.makedirs(OUTDIR, exist_ok=True)
    say = Tee(LOG_PATH)
    started = datetime.datetime.now()
    say(f"# Mitutoyo 500-171-30 / 959149 SPC port probe -- {started:%Y-%m-%d %H:%M:%S}")
    say(f"# pull-up {args.rpullup/1000:.0f} kOhm to {args.rail:.2f} V; REQ is never driven")

    dmm = DMM()
    say(f"[dmm] {dmm.identify()}")
    dmm.set_function("VOLT_DC")
    psu = PSU()
    say(f"[psu] {psu.identify()}")

    if not args.skip_a:
        phase_a(dmm, say)
    phase_b(dmm, say)
    phase_c(psu, dmm, say, args.rail, args.rpullup)

    ended = datetime.datetime.now()
    say(f"\n# finished {ended:%Y-%m-%d %H:%M:%S} (elapsed {ended - started})")
    say("# next: spc_capture.py -- scope one frame and pin down bit rate, edge and polarity")
    archive = os.path.join(OUTDIR, f"port_probe_{started:%Y-%m-%d_%H%M%S}.txt")
    shutil.copy(LOG_PATH, archive)
    print(f"\narchived to {archive}")


if __name__ == "__main__":
    main()
