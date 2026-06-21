import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def load(ch):
    raw = np.frombuffer(open(f"cap_ch{ch}.bin","rb").read(), dtype=np.uint8).astype(np.float64)
    pre = open(f"cap_ch{ch}.pre").read().split(",")
    xinc=float(pre[4]); yinc=float(pre[7]); yorig=float(pre[8]); yref=float(pre[9])
    return (raw - yref - yorig)*yinc, xinc

data_v, xinc = load(1)   # pin3 DATA
clk_v, _ = load(2)       # pin2 CLOCK
t = np.arange(len(clk_v))*xinc*1e3  # ms

# overview
fig, ax = plt.subplots(2,1, figsize=(12,5), sharex=True)
ax[0].plot(t, clk_v, lw=0.5, color="tab:blue"); ax[0].set_ylabel("CLK (pin2) V"); ax[0].grid(alpha=.3)
ax[1].plot(t, data_v, lw=0.5, color="tab:orange"); ax[1].set_ylabel("DATA (pin3) V"); ax[1].set_xlabel("ms"); ax[1].grid(alpha=.3)
ax[0].set_title("Full 160 ms capture")
fig.tight_layout(); fig.savefig("plot_overview.png", dpi=110)

# zoom on the burst near 78 ms
lo, hi = 77.5e-3, 85.5e-3
i0, i1 = int(lo/xinc), int(hi/xinc)
fig, ax = plt.subplots(figsize=(13,4))
ax.plot(t[i0:i1], clk_v[i0:i1], lw=0.9, label="CLK (pin2)")
ax.plot(t[i0:i1], data_v[i0:i1]+3.3, lw=0.9, label="DATA (pin3) +3.3V")
ax.set_xlabel("ms"); ax.set_title("24-bit burst (clock above 1.5V threshold = bit edges)")
ax.grid(alpha=.3); ax.legend(loc="upper right")
fig.tight_layout(); fig.savefig("plot_burst.png", dpi=120)
print("wrote plot_overview.png, plot_burst.png")
