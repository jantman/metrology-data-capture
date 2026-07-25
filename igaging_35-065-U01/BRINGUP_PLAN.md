# Bench Bring-Up Plan — iGaging 35-065-U01 Clock Injection

> **STATUS 2026-07-25 — clock injection EXHAUSTED, all negative. Read §11.7–§11.10 of
> `claude_desktop_initial_investigation.md` before doing anything here.** Two full bench
> sessions drove the mic every way we can: every pin as clock in every CLK/DATA/VDD role
> assignment (6/6 permutations), continuous + burst (idle high & low), 0.2–9 kHz, with/without
> VDD on each pin, with/without the DATA button (active + passive). **Result: the mic never
> actively drives any connector pin — only passive crosstalk, everywhere.** So the Phase-A
> "find CLK/DATA by injecting a clock" premise below did NOT pan out for this unit; Phases B/C
> are blocked until something makes a pin actually drive.
>
> Instrument corrections that supersede the text below: AWG raw-SCPI port is **5025** (not
> 5555); DHO814 timebase mode is `:TIMebase:MODE MAIN`; **High-Z is `:OUTPut:LOAD INF`** —
> the spelled-out `INFinity` mis-parses to a 1 Ω load and over-drives the pins (see §11.8).
>
> **Next (see §11.10):** (1) clock/listen while the spindle MOVES — the one untested variable
> (every test was on a static reading); (2) if still dead, reconsider whether this port needs
> the genuine host cable (`100-700-USB-MC`) rather than more injection permutations.

Execution plan for the next bench session. Goal: **make the mic talk and fully decode its
21-bit clock/data protocol.** Passive reverse-engineering is exhausted (the device is
host-clocked — see `claude_desktop_initial_investigation.md` §11.4); the only way forward is
to drive a clock in and watch it respond.

New this session: a **Rigol DG902 Pro AWG** at `rigol-awg.jasonantman.com` for clock
injection, alongside the **Rigol DHO814 scope** (up to 4 probes) at
`rigol-oscope.jasonantman.com:5555`. Both are driven headlessly over the LAN from Bash
(needs `dangerouslyDisableSandbox`).

---

## 0. What we already know (carried in from §11)

- **Pins 4 and 5 = GND** (tied together, = battery negative). Grounds go here.
- **Signal lines are pins 1, 2, 3** — which is CLK vs DATA vs 3rd is **unknown**. They float
  at idle (no internal pull-ups). Standard Micro-USB pin roles do **not** apply.
- **No supply rail on the connector**; the mic self-powers from its CR2032 (~3 V). The logic
  rail is internal only — **DATA's high level, once it responds, reveals the rail voltage.**
- **Host-clocked:** silent until an external clock is driven in.
- **Working protocol hypothesis** (to confirm): 21 bits, LSB-first, one's-complement signed,
  value = raw absolute encoder ticks (~4030 ticks/mm), no units/zero in the stream.

---

## 1. Safety model (why a wrong guess is harmless)

Two independent guards make it safe to probe an unknown pinout at an unknown voltage:

1. **~1–2.2 kΩ series resistor** between the AWG and the driven pin. If we accidentally drive
   an *output* (DATA), contention current is bounded to ≈ 3 V ÷ 1 kΩ = **3 mA** — a no-op that
   CMOS shrugs off. A wrong guess simply produces no response.
2. **Start at 1.5 V and ramp** toward the **3.0 V battery ceiling, never above.** At ≤ 1.5 V we
   cannot overvoltage any pin. A 1.5 V-rail part answers at 1.5 V; if it stays silent, it isn't
   a 1.5 V part, so ramping higher can't overvoltage it. Protection diodes + the resistor keep
   clamp current < 1 mA even in the paranoid case.

**AWG output impedance MUST be High-Z** (`:OUTPut:IMPedance INFinity`). If the AWG assumes a
50 Ω load but sees high impedance, the actual pin voltage **doubles** (1.5 V → 3.0 V). High-Z
makes commanded amplitude equal the amplitude at the pin. `scpi_lib.Awg` sets this
automatically; `clock_injection.py` also refuses any amplitude above `--max-volts` (default 3.0).

---

## 2. Equipment & wiring

| Role | Instrument | Address |
|---|---|---|
| Clock source | Rigol DG902 Pro AWG | `rigol-awg.jasonantman.com` (port **assumed 5555 — verify**) |
| Capture | Rigol DHO814 scope | `rigol-oscope.jasonantman.com:5555` (confirmed) |

- Micro-USB-B **female breakout** in the mic (battery in, case closed).
- **AWG output → ~1 kΩ (or 2.2 kΩ) series resistor → one candidate signal pin.**
- **Scope: 4 probes, fixed map — only the single AWG lead moves between runs:**

  | Scope CH | Probe to | Purpose |
  |---|---|---|
  | CH1 | connector **pin 1** | watch |
  | CH2 | connector **pin 2** | watch |
  | CH3 | connector **pin 3** | watch |
  | CH4 | **AWG output** (source side of the resistor) | commanded-clock monitor |

- **AWG ground clip AND all scope probe grounds → connector pin 4** (= pin 5 = battery −).
- All 1× probes, DC coupled.

With all three signal pins on the scope at once, **one capture identifies everything**: the
driven pin shows the clock, and whichever other pin bursts in sync is DATA. Rotating the AWG
lead through pins 1→2→3 (three runs max) is guaranteed to find the CLK/DATA pair.

---

## 3. Pre-flight checklist (do first, ~5 min)

1. `python scpi_lib.py awg` → confirm `*IDN?` returns the DG902 Pro. **If it hangs or refuses,
   the raw-SCPI port isn't 5555** — check the AWG's I/O config (Utility → I/O), then set `PORT`
   or pass a host:port. Rigol sometimes uses a different raw-socket port on newer models.
2. `python scpi_lib.py scope` → confirm the DHO814 `*IDN?` (known-good).
3. Meter the series resistor is actually in-line and grounds are on pin 4.
4. **Set the mic to a non-round, non-zero reading** (e.g. spindle a few mm open) — a static
   value of exactly 0 (all-zero DATA) defeats the autocorrelation frame-length finder in
   step 5. Any structured value works.

---

## 4. Phase A — Find CLK / DATA and the logic level

Drive a continuous ~9 kHz clock and ramp amplitude, watching for a response.

```
python clock_injection.py --drive-pin 1        # AWG lead on pin 1
python clock_injection.py --drive-pin 2        # then move lead to pin 2
python clock_injection.py --drive-pin 3        # then pin 3
```

Each run: ramps HIGH level `1.5 → 1.8 → 2.2 → 2.7 → 3.0 V`, single-shot captures all 4
channels at each level, saves to `captures/inj_p<pin>_<amp>v_ch{1..4}.{bin,pre}` + a
screenshot, and prints per-channel transition counts. **It stops at the first amplitude where a
non-driven pin shows clock-synchronous activity** (add `--all-levels` to capture every step).

**Decision tree:**
- **A response appears** → the **driven pin = CLK**, the **responding pin = DATA**, the **third
  = REQ/NC**. Record the amplitude at which it first responded and **DATA's high level = the
  internal logic rail.** Proceed to Phase B.
- **No response on any of pins 1/2/3 at up to 3.0 V** → reconsider: try the **falling/other
  clock edge isn't the issue here** (we're driving, not sampling) — instead try
  (a) a slower clock `--freq 1000`, (b) a burst instead of continuous (some scales need a gap
  to frame — see Phase C note), (c) confirm the resistor/grounds, (d) verify the mic is ON and
  not auto-sleeping (tap a button between captures).

Useful variants:
```
python clock_injection.py --drive-pin 1 --freq 2000 --amplitudes 1.5,2.0,2.5,3.0 --all-levels
```

---

## 5. Phase B — Recover framing, bit order, sign

Analyze the capture that responded (offline, no hardware):

```
python analyze_capture.py captures/inj_p1_2.2v --clk-pin 1 --data-pin 3
```

It will:
- Digitize all channels, confirm which is the regular clock.
- Sample DATA on **both** clock edges (reports which edge gives a clean, stable bit stream →
  that's the valid sampling edge).
- **Autocorrelate the DATA bit stream to find the frame length** — with a static reading and a
  continuous clock, DATA repeats every frame. Expect the period to lock at **21** (score ≈ 1.0).
- Print candidate 21-bit frames decoded as **one's-** and **two's-complement**, LSB-first, so
  you can eyeball which is sane.

Confirm and write down: **frame length, valid clock edge, bit order (LSB-first?), sign
encoding.** Then pin those into `igaging_decode.py` (`FRAME_BITS`, `LSB_FIRST`,
`SIGN_ENCODING`).

If autocorrelation is noisy: re-run Phase A capture with the spindle at a *different* structured
value, or force `--framelen 21` / `--edge rising` to test the hypothesis directly.

---

## 6. Phase C — Ground-truth capture & calibration

Once framing is known, take a set of captures at **known displayed readings** (mirror of the
LS-20 `gt_capture.py` workflow):

1. For each of several spindle positions, **record the LCD reading** and capture DATA.
   Include: fully closed/zeroed, and known **gauge-block** sizes (e.g. 1.000 mm, 5.000 mm,
   10.000 mm) across the 0–25 mm range for a linearity check.
2. Decode each to raw ticks. Fit **ticks/mm** (expected ≈ 4030) and confirm linearity.
3. Verify **sign** by going negative (open past your chosen zero) and confirm the sign bit.
4. Confirm the stream is **absolute encoder ticks**, not the display value (zero/units are done
   downstream) — i.e. the mic's zero/units/ABS-INC buttons should NOT change the tick↔position
   relationship, only the LCD.

Record each `(wire-order bitstring → LCD reading)` pair into `igaging_decode.GROUND_TRUTH` so
the decoder self-tests, and set `TICKS_PER_MM` from the fit.

> **Note on burst vs continuous clocking:** for discovery we drive a *continuous* clock and find
> framing by autocorrelation. The "proper" host protocol may clock **bursts of 21 pulses with an
> inter-frame gap**. Once framing is confirmed we can optionally switch the AWG to a gated/burst
> mode to read exactly one clean frame per burst — but continuous + autocorrelation is enough to
> decode, and the eventual MCU firmware will generate its own bursts.

---

## 7. Deliverables / success criteria

- [ ] AWG SCPI reachable; port confirmed.
- [ ] CLK, DATA, and 3rd pin identified (Phase A).
- [ ] Internal logic rail voltage read off DATA's high level.
- [ ] Frame length, valid clock edge, bit order, sign encoding confirmed (Phase B).
- [ ] `ticks/mm` calibrated against gauge blocks; linearity + sign verified (Phase C).
- [ ] `igaging_decode.py` constants pinned + `GROUND_TRUTH` populated and passing.
- [ ] Findings written back into `claude_desktop_initial_investigation.md` §11 (this is the
      canonical bench log; §11.5 predicted this exact procedure).

After that, the MCU front-end is a straight port of the LS-20 firmware pattern
(`mxmoonfree_LS-20-6/firmware/`), except **this mic is host-clocked** — the ESP32 must *generate*
the clock burst and sample DATA, rather than passively listening. That's the follow-on project.

---

## 8. Files in this directory

| File | Purpose |
|---|---|
| `BRINGUP_PLAN.md` | This plan. |
| `scpi_lib.py` | Raw-socket SCPI clients: `Scope` (DHO814) + `Awg` (DG902 Pro). Run directly to `*IDN?`-check either. |
| `clock_injection.py` | Phase A: drive AWG clock into a pin, 4-channel single-shot capture with amplitude ramp + response detection. |
| `analyze_capture.py` | Phase B: offline — digitize, ID clock, sample DATA per edge, autocorrelate frame length, decode candidate frames. |
| `igaging_decode.py` | Reference decoder (hypothesis constants; pin them + fill `GROUND_TRUTH` in Phase C). Basis for the firmware port. |
| `captures/` | Raw scope captures (git-ignored). |
| `claude_desktop_initial_investigation.md` | Canonical bench log / findings (§11 wins over §4–5). Write results here. |
| `PICT00*.jpg` | Teardown photos. |
