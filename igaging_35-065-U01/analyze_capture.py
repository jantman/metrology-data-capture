"""Offline analysis of a 4-channel clock-injection capture (see BRINGUP_PLAN.md).

Given a capture prefix written by clock_injection.py (e.g. captures/inj_p1_2.2v), this:
  1. Loads + scales every channel (BYTE data via its preamble).
  2. Digitizes each to logic 0/1 at mid-swing.
  3. Identifies CLK (most-regular periodic channel, or --clk-pin) and reads DATA on each
     clock edge (tries BOTH edges), producing a raw bit sequence.
  4. Finds the frame length by autocorrelation of the DATA bit sequence — with a static
     reading and a continuous clock, DATA repeats every frame (expected 21 bits for the
     iGaging protocol). Confirms/reports the true frame length.
  5. Decodes candidate frames as LSB-first one's-complement signed integers (the reported
     iGaging encoding) and prints them so you can correlate against the LCD + gauge blocks.

Nothing here assumes the pinout or bit encoding is already proven — it reports the evidence.

Usage:
    python analyze_capture.py captures/inj_p1_2.2v
    python analyze_capture.py captures/inj_p1_2.2v --clk-pin 1 --data-pin 3
    python analyze_capture.py captures/inj_p1_2.2v --framelen 21 --edge rising
"""
import argparse
import statistics

PIN_CHANS = {1: 1, 2: 2, 3: 3}  # connector pin -> scope channel (CH4 = AWG monitor)


def load_channel(prefix, ch):
    with open(f"{prefix}_ch{ch}.pre") as f:
        pre = f.read().strip()
    with open(f"{prefix}_ch{ch}.bin", "rb") as f:
        raw = f.read()
    p = pre.split(",")
    xinc = float(p[4])
    yinc, yorig, yref = float(p[7]), float(p[8]), float(p[9])
    volts = [(b - yorig - yref) * yinc for b in raw]
    return {"xinc": xinc, "volts": volts}


def digitize(volts):
    if not volts:
        return [], 0.0
    lo, hi = min(volts), max(volts)
    vpp = hi - lo
    if vpp < 0.2:
        return [0] * len(volts), vpp
    mid = lo + vpp / 2
    hyst = vpp * 0.1
    bits = []
    state = 0
    for v in volts:
        if v > mid + hyst:
            state = 1
        elif v < mid - hyst:
            state = 0
        bits.append(state)
    return bits, vpp


def edges(bits, rising=True):
    out = []
    for i in range(1, len(bits)):
        if rising and bits[i - 1] == 0 and bits[i] == 1:
            out.append(i)
        elif not rising and bits[i - 1] == 1 and bits[i] == 0:
            out.append(i)
    return out


def regularity(edge_idx):
    """Lower coefficient-of-variation of edge spacing == more clock-like. None if too few."""
    if len(edge_idx) < 5:
        return None
    gaps = [b - a for a, b in zip(edge_idx, edge_idx[1:])]
    m = statistics.mean(gaps)
    if m == 0:
        return None
    return statistics.pstdev(gaps) / m


def sample_data_on_clock(data_bits, clk_edges):
    """Return the DATA logic level sampled at each clock edge."""
    return [data_bits[i] for i in clk_edges if i < len(data_bits)]


def autocorr_period(seq, maxlen=40):
    """Find the smallest lag (>=2) that best repeats the sequence. Returns (lag, score)."""
    n = len(seq)
    if n < maxlen * 2:
        maxlen = max(2, n // 2)
    best = (None, -1.0)
    for lag in range(2, maxlen + 1):
        matches = sum(1 for i in range(n - lag) if seq[i] == seq[i + lag])
        score = matches / (n - lag) if n - lag else 0
        if score > best[1]:
            best = (lag, score)
    return best


def ones_complement_signed(bits):
    """LSB-first bits -> signed int under one's-complement (MSB = sign)."""
    n = len(bits)
    val = sum(b << i for i, b in enumerate(bits))
    if bits[-1] == 1:  # negative in one's complement
        val = -((~val) & ((1 << n) - 1))
    return val


def twos_complement_signed(bits):
    n = len(bits)
    val = sum(b << i for i, b in enumerate(bits))
    if bits[-1] == 1:
        val -= (1 << n)
    return val


def analyze(prefix, clk_pin=None, data_pin=None, framelen=None, edge=None):
    chans = {p: load_channel(prefix, ch) for p, ch in PIN_CHANS.items()}
    digi = {}
    print(f"== {prefix} ==")
    for p, c in chans.items():
        bits, vpp = digitize(c["volts"])
        re_ = regularity(edges(bits, rising=True))
        digi[p] = bits
        reg_s = f"{re_:.3f}" if re_ is not None else "n/a"
        print(f"  pin{p}: vpp={vpp:.2f}V  rising-edges={len(edges(bits))}  "
              f"edge-regularity(cv)={reg_s}  (lower=more clock-like)")

    # Pick CLK = most regular channel unless overridden.
    if clk_pin is None:
        scored = [(regularity(edges(digi[p])), p) for p in PIN_CHANS]
        scored = [(r, p) for r, p in scored if r is not None]
        clk_pin = min(scored)[1] if scored else list(PIN_CHANS)[0]
    data_pins = [data_pin] if data_pin else [p for p in PIN_CHANS if p != clk_pin]
    print(f"\n  CLK = pin{clk_pin}; DATA candidate(s) = {data_pins}")

    xinc = chans[clk_pin]["xinc"]
    for pol in ([edge] if edge else ["rising", "falling"]):
        clk_e = edges(digi[clk_pin], rising=(pol == "rising"))
        if len(clk_e) < 4:
            continue
        gaps = [b - a for a, b in zip(clk_e, clk_e[1:])]
        est_hz = 1.0 / (statistics.mean(gaps) * xinc) if gaps and xinc else 0
        print(f"\n  -- sampling DATA on CLK {pol} edges ({len(clk_e)} edges, "
              f"~{est_hz:.0f} Hz) --")
        for dp in data_pins:
            seq = sample_data_on_clock(digi[dp], clk_e)
            if len(seq) < 8:
                print(f"    pin{dp}: only {len(seq)} samples, skipping")
                continue
            lag, score = autocorr_period(seq)
            fl = framelen or (lag if score >= 0.9 else None)
            head = "".join(str(b) for b in seq[:60])
            print(f"    pin{dp}: {len(seq)} bits, autocorr period={lag} (score={score:.2f})"
                  f"{'  <-- likely frame len' if score >= 0.9 else ''}")
            print(f"      bits[0:60]: {head}")
            if fl and fl >= 4:
                # Try each phase alignment; decode the first stable frame under both encodings.
                for phase in range(min(fl, 4)):
                    frame = seq[phase:phase + fl]
                    if len(frame) < fl:
                        break
                    b = "".join(str(x) for x in frame)
                    print(f"      frame@phase{phase} [{fl}b LSB-first] {b}"
                          f"  ones'c={ones_complement_signed(frame):>10}"
                          f"  twos'c={twos_complement_signed(frame):>10}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prefix", help="capture prefix, e.g. captures/inj_p1_2.2v")
    ap.add_argument("--clk-pin", type=int, choices=(1, 2, 3), default=None)
    ap.add_argument("--data-pin", type=int, choices=(1, 2, 3), default=None)
    ap.add_argument("--framelen", type=int, default=None, help="force frame length (e.g. 21)")
    ap.add_argument("--edge", choices=("rising", "falling"), default=None)
    args = ap.parse_args()
    analyze(args.prefix, args.clk_pin, args.data_pin, args.framelen, args.edge)


if __name__ == "__main__":
    main()
