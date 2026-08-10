"""STEP 3+4 of bring-up: scope one Digimatic frame and pin down the four unknowns the
firmware needs -- bit rate, which clock edge carries valid data, wire polarity, and whether
this caliper really sends 52 bits.

Usage:  python3 spc_capture.py "<label>"        # label = the LCD reading, e.g. "10.00mm"
        python3 spc_capture.py "0.00mm" --level 0.75

Arm it, then press the 959149's DATA button. The script triggers on the CK falling edge,
pulls both channels out of deep memory, and reports:

  * measured logic levels on both lines (this is also an independent check on port_probe.py's
    open-collector verdict: a true open collector pulled to 3.3 V swings the full rail)
  * edge count and bit period statistics -- 52 edges is the whole ballgame
  * DATA sampled at BOTH the falling and the rising clock edge, decoded BOTH ways, with wire
    polarity inferred from the 0xFFFF preamble

Exactly one of the four (edge x polarity) combinations should produce a frame whose preamble
and BCD digits are valid AND whose value matches the label you typed in. That combination is
what goes into the firmware. Run it once per known LCD reading; rows accumulate in gt_log.csv.

Channels:  CH1 = DATA (Digimatic pin 2)   CH2 = CK (Digimatic pin 3)

Networking to the scope needs Bash `dangerouslyDisableSandbox`.
"""
import argparse
import csv
import os
import statistics
import sys
import time

import numpy as np

from digimatic_decode import BITS_PER_FRAME, FrameError, decode_frame
from scope_lib import Scope

OUTDIR = "findings"
GT_LOG = "gt_log.csv"


def read_raw(s, ch, total, chunk=200_000):
    """Pull a whole channel out of deep memory in chunks; returns (preamble, bytes)."""
    s.write(f":WAVeform:SOURce CHANnel{ch}")
    s.write(":WAVeform:MODE RAW")
    s.write(":WAVeform:FORMat BYTE")
    s.write(":WAVeform:STARt 1")
    s.write(f":WAVeform:STOP {min(chunk, total)}")
    pre = s.query(":WAVeform:PREamble?")
    data = bytearray()
    start = 1
    while start <= total:
        stop = min(start + chunk - 1, total)
        s.write(f":WAVeform:STARt {start}")
        s.write(f":WAVeform:STOP {stop}")
        data += s.query_block(":WAVeform:DATA?")
        start = stop + 1
    return pre, bytes(data)


def to_volts(raw, pre):
    f = [float(x) for x in pre.split(",")]
    yinc, yorig, yref = f[7], f[8], f[9]
    return (np.frombuffer(raw, dtype=np.uint8).astype(np.float64) - yorig - yref) * yinc


def digitize(v):
    """Threshold at the midpoint of the observed swing (robust to whatever rail we ended up
    with -- 1.5 V clamped or 3.3 V open-collector both work)."""
    lo, hi = float(v.min()), float(v.max())
    return (v > (lo + hi) / 2).astype(np.int8), lo, hi


def split_bursts(edges, xinc, gap_s=5e-3):
    """Group clock edges into frames. Intra-frame bit periods are sub-millisecond; the gap
    between two frames (one per REQ assertion) is orders of magnitude longer."""
    gap = gap_s / xinc
    bursts, cur = [], [edges[0]]
    for e in edges[1:]:
        if e - cur[-1] > gap:
            bursts.append(np.array(cur))
            cur = [e]
        else:
            cur.append(e)
    bursts.append(np.array(cur))
    return bursts


def try_decode(bits):
    """Decode with polarity inferred from the preamble; return (text, note)."""
    if len(bits) != BITS_PER_FRAME:
        return None, f"{len(bits)} bits (need {BITS_PER_FRAME})"
    try:
        r = decode_frame(bits)
    except FrameError as e:
        return None, str(e)
    pol = "inverted" if r.inverted else "as-wired"
    return f"{r.text} {r.unit}", f"polarity={pol} nibbles={''.join(f'{n:X}' for n in r.nibbles)}"


def analyze(datd, ckd, xinc, out=print):
    """Turn digitized CK/DATA traces into decoded frames. Split out from main() so it can be
    exercised offline against a synthesized waveform (see selftest_analyze.py) instead of only
    ever running once, live, with the caliper in one hand."""
    fall = np.where(np.diff(ckd) == -1)[0] + 1
    rise = np.where(np.diff(ckd) == 1)[0] + 1
    if len(fall) == 0:
        out("  !! no clock edges in the capture")
        return []

    rows = []
    for bi, burst in enumerate(split_bursts(fall, xinc)):
        periods = np.diff(burst) * xinc
        out(f"\n  -- burst {bi}: {len(burst)} falling edges "
            f"(expect {BITS_PER_FRAME}), span {(burst[-1]-burst[0])*xinc*1e3:.2f} ms")
        if len(periods):
            out(f"     bit period: median {statistics.median(periods)*1e6:.1f} us, "
                f"min {periods.min()*1e6:.1f}, max {periods.max()*1e6:.1f} "
                f"-> ~{1/statistics.median(periods):.0f} Hz clock")
            big = periods[periods > 3 * statistics.median(periods)]
            if len(big):
                out(f"     {len(big)} intra-frame gap(s) > 3x median, largest "
                    f"{big.max()*1e3:.2f} ms -- firmware's frame-gap threshold must exceed this")

        rin = rise[(rise >= burst[0]) & (rise <= burst[-1])]
        bits_f = [int(datd[i]) for i in burst]
        bits_r = [int(datd[i]) for i in rin]
        sf, sr = "".join(map(str, bits_f)), "".join(map(str, bits_r))
        out(f"     DATA @ CK falling ({len(bits_f)}): {sf}")
        out(f"     DATA @ CK rising  ({len(bits_r)}): {sr}")
        for name, bits in (("falling", bits_f), ("rising", bits_r)):
            text, note = try_decode(bits)
            out(f"     [{name:7}] " + (f"{text:>14}   {note}" if text else f"no decode: {note}"))
            if text:
                rows.append((bi, name, text, note, sf if name == "falling" else sr))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("label", nargs="?", default="unlabeled",
                    help="the LCD reading at capture time, e.g. 10.00mm")
    ap.add_argument("--level", type=float, default=0.75,
                    help="trigger level, volts (0.75 suits both a 1.5 V clamped line and a "
                         "3.3 V open-collector line)")
    ap.add_argument("--tscale", type=float, default=0.005,
                    help="s/div; the default spans ~60 ms, comfortably more than one ~34 ms frame")
    ap.add_argument("--vscale", type=float, default=0.5, help="V/div on both channels")
    ap.add_argument("--wait", type=float, default=30.0, help="seconds to wait for the trigger")
    args = ap.parse_args()

    os.makedirs(OUTDIR, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "+-._" else "_" for c in args.label)

    s = Scope(timeout=30)
    s.write(":RUN")
    s.write(":ACQuire:MDEPth 1000000")
    s.write(f":TIMebase:MAIN:SCALe {args.tscale}")
    s.write(":TIMebase:MAIN:OFFSet 0")
    for ch in (1, 2):
        s.write(f":CHANnel{ch}:DISPlay ON")
        s.write(f":CHANnel{ch}:COUPling DC")
        s.write(f":CHANnel{ch}:SCALe {args.vscale}")
        s.write(f":CHANnel{ch}:OFFSet {-2 * args.vscale}")
    s.write(":TRIGger:MODE EDGE")
    s.write(":TRIGger:EDGE:SOURce CHANnel2")          # CK
    s.write(":TRIGger:EDGE:SLOPe NEGative")           # open-collector idle high -> assert low
    s.write(f":TRIGger:EDGE:LEVel {args.level}")
    s.write(":TRIGger:SWEep NORMal")
    time.sleep(0.3)
    s.write(":SINGle")
    time.sleep(0.2)

    print(f"\n*** ARMED -- press the 959149's DATA button now (label: {args.label}) ***")
    deadline = time.time() + args.wait
    status = None
    while time.time() < deadline:
        status = s.query(":TRIGger:STATus?")
        if status == "STOP":
            break
        time.sleep(0.1)
    if status != "STOP":
        print(f"!! no trigger (status={status}).")
        print("   Checks: caliper on? cable seated? trigger level below the idle high level?")
        print("   If CK idles LOW on your front end, re-run with --slope positive logic in mind.")
        s.close()
        sys.exit(1)

    total = int(float(s.query(":ACQuire:MDEPth?")))
    pre1, d1 = read_raw(s, 1, total)      # DATA
    pre2, d2 = read_raw(s, 2, total)      # CK
    s.close()

    p1 = os.path.join(OUTDIR, f"gt_{safe}_ch1_data.bin")
    p2 = os.path.join(OUTDIR, f"gt_{safe}_ch2_ck.bin")
    open(p1, "wb").write(d1)
    open(p2, "wb").write(d2)

    xinc = float(pre2.split(",")[4])
    dat_v, ck_v = to_volts(d1, pre1), to_volts(d2, pre2)
    datd, dlo, dhi = digitize(dat_v)
    ckd, clo, chi = digitize(ck_v)

    print(f"\n=== {args.label} ===   ({total} samples @ {xinc*1e9:.0f} ns)")
    print(f"  DATA swing: {dlo:+.2f} .. {dhi:+.2f} V      CK swing: {clo:+.2f} .. {chi:+.2f} V")
    if chi - clo < 0.8:
        print("  !! clock swing under 0.8 V -- front end is not delivering usable logic levels")
    if chi < 2.4:
        print("  ** note: CK high is below an ESP32-S3 VIH (~2.48 V). Direct-to-GPIO will NOT")
        print("     work with this front end; see README 'The open-drain question'.")

    rows = analyze(datd, ckd, xinc)

    if not rows:
        print("\n  No combination decoded. Most likely causes, in order: wrong pin map (CK and")
        print("  DATA swapped), front end not passing logic levels, or this tool does not use")
        print("  the 13-nibble frame. The raw .bin files are saved -- re-analyze offline.")

    new = not os.path.exists(GT_LOG)
    with open(GT_LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["label", "burst", "edge", "decoded", "note", "bits"])
        for r in rows or [("", "", "", "NO DECODE", "", "")]:
            w.writerow([args.label, *r])
    print(f"\n  raw: {p1} / {p2}    logged to {GT_LOG}")
    print("  Confirm the decoded value equals the label before trusting it.")


if __name__ == "__main__":
    main()
