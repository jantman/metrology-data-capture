"""Analyze + decode a DHO814 raw capture of the Mxmoonfree LS-20 caliper data port.

cap_ch1.bin = Pin 3 = DATA (yellow / CH1)
cap_ch2.bin = Pin 2 = CLOCK (cyan / CH2)
"""
import numpy as np

def load(ch):
    raw = np.frombuffer(open(f"cap_ch{ch}.bin", "rb").read(), dtype=np.uint8).astype(np.float64)
    pre = open(f"cap_ch{ch}.pre").read().split(",")
    xinc = float(pre[4]); yinc = float(pre[7]); yorig = float(pre[8]); yref = float(pre[9])
    volts = (raw - yref - yorig) * yinc
    return volts, xinc

data_v, xinc = load(1)   # DATA, pin3
clk_v, _ = load(2)       # CLOCK, pin2
N = len(clk_v)
print(f"samples={N}  xinc={xinc*1e9:.1f} ns  window={N*xinc*1e3:.1f} ms")

def digitize(v):
    vmin, vmax = v.min(), v.max()
    thr = (vmin + vmax) / 2
    return (v > thr).astype(np.int8), vmin, vmax, thr

clk, cmin, cmax, cthr = digitize(clk_v)
dat, dmin, dmax, dthr = digitize(data_v)
print(f"CLK  range {cmin:.2f}..{cmax:.2f} V  thr {cthr:.2f}")
print(f"DATA range {dmin:.2f}..{dmax:.2f} V  thr {dthr:.2f}")
print(f"CLK  idle (first 1000 samp mean level): {clk[:1000].mean():.2f}")
print(f"DATA idle (first 1000 samp mean level): {dat[:1000].mean():.2f}")

def edges(sig):
    d = np.diff(sig.astype(np.int8))
    rising = np.where(d == 1)[0] + 1
    falling = np.where(d == -1)[0] + 1
    return rising, falling

cr, cf = edges(clk)
print(f"\nCLOCK edges: {len(cr)} rising, {len(cf)} falling")

# clock pulse spacing (use falling edges = one per bit)
if len(cf) > 2:
    iv = np.diff(cf) * xinc
    small = iv[iv < 5e-3]   # intra-burst
    big = iv[iv >= 5e-3]    # inter-burst gaps
    print(f"intra-burst bit period: median {np.median(small)*1e6:.2f} us "
          f"(min {small.min()*1e6:.2f}, max {small.max()*1e6:.2f}, n={len(small)})")
    if len(big):
        print(f"inter-burst gaps: {[f'{g*1e3:.2f}ms' for g in big[:10]]} (n={len(big)})")

# segment into bursts by gap in falling edges
GAP = 5e-3 / xinc   # 5 ms in samples
bursts = []
cur = [cf[0]] if len(cf) else []
for e in cf[1:]:
    if e - cur[-1] > GAP:
        bursts.append(cur); cur = [e]
    else:
        cur.append(e)
if cur:
    bursts.append(cur)
print(f"\nbursts found: {len(bursts)}; bits/burst: {[len(b) for b in bursts]}")

# decode each burst: sample DATA at clock rising and falling edges
def sample_at(edge_idxs):
    return [int(dat[i]) for i in edge_idxs]

for bi, b in enumerate(bursts[:6]):
    b = np.array(b)
    # falling-edge sampling (read on falling)
    bits_f = sample_at(b)
    # rising-edge sampling within same time span
    lo, hi = b[0]-2, b[-1]+2
    rmask = (cr >= lo) & (cr <= hi)
    bits_r = sample_at(cr[rmask])
    sf = "".join(str(x) for x in bits_f)
    sr = "".join(str(x) for x in bits_r)
    print(f"\nburst {bi}: {len(b)} bits, t0={b[0]*xinc*1e3:.2f}ms")
    print(f"  data@falling: {sf}")
    print(f"  data@rising : {sr}")

# also report clock high/low duty within a burst
if bursts:
    b = np.array(bursts[0])
    seg = clk[b[0]-5:b[-1]+5]
    print(f"\nfirst-burst clock samples high fraction: {seg.mean():.2f}")
