# Bench Log — iGaging 35-065-U01 data port

> Live reverse-engineering record for this specific 35-065-U01. Log started 2026-06-21.
>
> **Section numbers are historical and deliberately non-sequential.** These were §11.x of the
> old `claude_desktop_initial_investigation.md`; they are preserved verbatim because script
> docstrings, commit messages, and `review.md` all cite them. **Sections now appear in
> chronological order** (§11.12/§11.13 precede §11.14–§11.16, which is the order the work
> actually happened — the old file had them reversed).
>
> **Read `review.md` alongside this file.** It audits these findings against the raw captures
> and identifies which conclusions do not survive that audit.
>
> Protocol background: `igaging_protcol_research.md`. Current state: `STATUS.md`.

---

### 11.1 Equipment
- Micro-USB-B **female breakout** — exposes all 5 connector pins externally with the **case
  closed** (no need to keep opening the mic).
- Multimeter — continuity + DC volts.
- **Rigol DHO814** oscilloscope with **1X** passive probes.
- **AFG (arbitrary function generator)** — *ordered 2026-06-21, ETA ~early July 2026.* Required
  for the clock-injection step (§11.5); active bring-up is paused until it arrives.

### 11.2 Corrected pinout (this unit)
Standard Micro-USB pin roles do **not** apply — this is a proprietary mapping, and it differs
from the §4 table.

| Connector pin | THIS unit | §4 had assumed | Status |
|---|---|---|---|
| 1 | Signal — CLK / DATA / 3rd (TBD) | VDD | floats at idle |
| 2 | Signal — CLK / DATA / 3rd (TBD) | CLK / SSY | floats at idle |
| 3 | Signal — CLK / DATA / 3rd (TBD) | DATA | floats at idle |
| 4 | **GND** | REQ | confirmed |
| 5 | **GND** (tied to pin 4) | GND | confirmed |

### 11.3 Confirmed findings
- **Pins 4 and 5 are both GND** — direct continuity between them and to battery negative.
- **The three signal lines are pins 1, 2, 3** (by elimination). With the device ON they all
  **float** at ~−0.02 V — no internal pull-ups (external pull-ups will be needed, per §6).
- **No VDD/battery rail is exposed on the connector.** Battery+ rings to no connector pin; the
  mic is **self-powered by its CR2032 (3 V)**. The logic rail is internal only.
- **The device is HOST-CLOCKED** (a clock-slave): it transmits nothing until an external clock
  is driven in. Evidence in §11.4.
- **Controller is an unmarked COB epoxy blob** on the LCD side of the PCB — no part number is
  obtainable, so there's no value in removing the board. The accessible (battery/USB) side has
  only passives (R1/R2, C4/C5), two transistors (Q1/Q2), the USB jack, battery contacts, the
  sensor FPC connector, and a **config solder-jumper matrix `J10/J11…J60/J61`** (this is a
  shared iGaging sensor board; the jumpers select the product/protocol variant).
  Photos: `PICT0049/0056/0057.jpg`.

### 11.4 What's been tried (and what it ruled out)
1. **Meter pin 1 ↔ pin 5, battery in:** 0 V → pin 1 is **not** VDD (kills the §4 assumption).
2. **DC sweep, device ON, GND → pins 1/2/3:** all float ~−0.02 V → no exposed rail, no pull-ups.
3. **Continuity:** pin 4 = GND, pin 5 = GND (tied to pin 4), battery+ → no connector pin.
4. **Passive scope** (DHO814, 1X, DC, 500 mV/div, 1 ms/div), **armed single-shot edge captures
   on pins 1/2/3/5:** **nothing triggered** on rising edge while pressing Data, moving the
   spindle, toggling inch/mm, and toggling ABS/INC. A second pass with a **falling-edge,
   0.2 V** trigger likewise **caught nothing** — the passive door is now closed.
   - **Interpretation:** a free-running design would have emitted periodic bursts here; silence
     across every provocation (both edge polarities, down to 0.2 V) means it's **host-clocked**.
     Passive observation is exhausted; next move is active clock injection (§11.5).

### 11.5 Next step — clock injection (when the AFG arrives)
**Goal:** make the mic talk, and in doing so identify **which of pins 1/2/3 is CLK vs DATA**
(and the 3rd line), read the **logic-high voltage** off DATA's swing, and confirm the **21-bit
framing**.

**Rig:**
- Breakout in the mic (battery in, case closed). **AFG ground and scope ground both to pin 4
  (or 5).**
- **AFG output → ~1 kΩ series resistor → the candidate CLK pin.** (The resistor is the safety
  element — see §11.6.)
- Scope (DC coupled) on the **other two** of pins 1/2/3. Start ~1 ms/div to see a whole frame,
  then zoom to ~20–50 µs/div to resolve individual bits.
- **AFG settings:** square wave, **~9 kHz**, **0 → 1.5 V** (1.5 Vpp, +0.75 V offset), ~50 %
  duty. A continuous clock is fine to start.

**Procedure:**
1. Drive **pin 1** as CLK at 1.5 V; watch pins 2 & 3 for a ~21-bit burst synchronized to the
   clock. No response → move the drive to **pin 2** (watch 1 & 3), then **pin 3** (watch 1 & 2).
2. If none of the three respond at 1.5 V, step the amplitude up — **1.8 → 2.2 → 2.7 → 3.0 V
   (battery ceiling, never exceed)** — repeating the 3-pin sweep at each level. **Stop the
   instant DATA responds.**
3. On response: the **driven pin = CLK**, the **responding pin = DATA**, the **third = REQ/NC**.
   Record **DATA's high level = the logic rail**, and note which clock edge the data is valid on.
4. Then sweep the clock rate to find the working range/tolerance, and capture a full frame to
   confirm **21 bits, LSB-first, one's-complement** (§7).

### 11.6 Why this is safe without knowing the pinout or the voltage
Safety does **not** depend on knowing either in advance — two techniques make a wrong guess
harmless:

- **Unknown pinout → the ~1 kΩ series resistor.** If you accidentally drive an *output* (DATA),
  the resistor bounds the contention current: worst case 3 V ÷ 1 kΩ = **3 mA**, which CMOS pins
  shrug off. A wrong guess is simply a no-op (no response) — that's exactly how you find CLK.
- **Unknown voltage → start at the 1.5 V floor and ramp.** The rail must be **1.5–3 V** (family
  range, single 3 V cell). At ≤ 1.5 V you **cannot** overvoltage any pin (you drive at most
  *equal* to Vdd). A 1.5 V-rail part *answers* a 1.5 V clock, so a response there means you're
  done at a provably-safe level. If it stays silent at 1.5 V on all three pins, it **isn't** a
  1.5 V part — so ramping toward the **3 V battery ceiling** can't overvoltage it.
- **Belt-and-suspenders:** even in the paranoid case (rail really 1.5 V, driven at 3 V), the
  pin's protection diode clamps to ~2 V and the resistor holds the clamp current **< 1 mA** —
  safe. Use **2.2 kΩ** for extra margin (edges stay clean at 9 kHz).
- **The device reveals the rail itself:** DATA's response amplitude *is* the logic voltage, so
  the last unknown resolves the moment it talks.
- **Caveat if a microcontroller is ever used as the clock instead of the AFG:** its GPIO (3.3 V
  ESP / 5 V Arduino) is too high to drive raw — put a resistor divider on it to reach the ~1.5 V
  start point. The AFG is preferred precisely because you dial the amplitude directly.

### 11.7 Bench session 2026-07-18 — clock injection (DG902 Pro + DHO814)

First live clock-injection session (per `BRINGUP_PLAN.md`). **Outcome: CLK/DATA not yet
confirmed — every stimulus so far yields only crosstalk. Leading unblock is powering pin 1
(VDD). See `PROTOCOL_RESEARCH.md` for the sourced protocol facts that reframed the work.**

**Instrument setup / gotchas fixed (in `scpi_lib.py`):**
- **DG902 Pro raw-SCPI port = 5025**, NOT 5555 (the scope's port). Baked into `AWG_PORT`.
- **DHO814 timebase mode** command is `:TIMebase:MODE MAIN` — `:TIMebase:MAIN:MODE` was
  rejected (`-100`) and threw "Remote Cmd Error" pop-ups (captures were still valid).
- **AWG High-Z** keyword is `:OUTPut:LOAD INFinity`; `:OUTPut:IMPedance` is rejected
  (`-113`). `set_highz()` had been silently failing, but amplitudes were correct anyway
  because the AWG's power-on default load is already High-Z (scope-verified 1:1).
- AWG burst: `:SOURce1:BURSt:*` + `:TRIGger1:SOURce IMMediate` (auto-repeat at INTernal:PERiod).

**What was tried and ruled out:**
1. **Continuous 9 kHz, each pin driven in turn (1.5→3.0 V ramp), watch the other two.** All
   three pins: **only crosstalk.** The non-driven pins swing a *fixed fraction* of the clock
   amplitude (pin-adjacency matrix ≈ 1↔2:0.20, 2↔3:0.20, 1↔3:0.10 — consistent with the pins
   in physical order 1-2-3). Fixed-fraction-of-clock ⇒ **the mic drives nothing**; the lines
   are floating and passively coupled. Wiring/grounds/series-R all validated by this.
2. **DATA-button "gate" hypothesis** (held button while clocking each pin): still crosstalk.
   **Passive self-clock test** (AWG off, sensitive NORMAL trigger, press DATA): no trigger.
   Research (below) confirms the on-body DATA button does **not** self-clock a frame — in the
   factory cable an MCU does the clocking; the button just triggers the PC keyboard-type.
3. **Burst framing + DATA pull-down** (21 cyc @ 9 kHz + ~7 ms gap into pin 2; measured
   **9.887 kΩ** pull-down pin 3→GND; mic **awake**): still crosstalk. (An earlier burst run was
   invalid — the mic had **auto-slept**; auto-off is **tens of minutes**, so sleep was not the
   systematic cause of the other negatives.)

**Online research (2026-07-18, two independent passes → `PROTOCOL_RESEARCH.md`):**
- Device = iGaging **"IP65 EZ Data Twin-Force"** micrometer; port = iGaging **21-bit**
  synchronous protocol, **host-clocked**, **no REQ line**. Not Mitutoyo SPC.
- Standard mapping: **pin1 = VDD, pin2 = CLOCK (drive), pin3 = DATA (read)**; LSB-first,
  ~9 kHz, 21 bits, raw absolute ticks ≈ 4030/mm. Sign encoding one's- vs two's-complement
  **disputed** — resolve empirically in Phase B/C.
- Official cable pinned down: **iGaging `100-700-USB-MC`** (Micro-USB variant; supersedes §8's
  guess). The plain-SPC `100-700-USB` is the wrong, incompatible one.

**Current leading hypothesis (why total silence on every pin):** pin 1 is a **VDD *input***,
not the exposed rail — §11.3 measured it floating ~0 V, and an exposed 3 V rail would read 3 V.
The encoder+LCD run off the CR2032 (display works), but the **CLK/DATA interface buffer is
likely powered from pin-1 VDD**, which we left floating ⇒ the interface never powers up ⇒
silence regardless of how we clock. This is the one explanation consistent with *every* pin
being dead.

**Next step (rig staged, not yet run):** supply **DC 3.0 V to pin 1** from AWG **CH2** (through
a small series R) while burst-clocking pin 2 and reading pin 3 — `vdd_burst_capture.py`. It
self-verifies the VDD level on the scope starting at a safe 1.0 V (aborts on voltage doubling)
before ramping. Pin-1 voltage **sagging under load = the interface is drawing current =
powering up** (good sign). If pin 1 holds VDD steady with still-crosstalk data, pin 1 is
likely NC and we revisit the clk/data pairing / a different enable.

**Session tooling added:** `button_capture.py` (button-gated), `passive_capture.py` (self-clock
probe), `burst_capture.py` (burst clock), `vdd_burst_capture.py` (VDD supply + burst),
`PROTOCOL_RESEARCH.md` (sourced protocol reference).

> **⚠ Correction (see §11.8):** the §11.7 claim that High-Z is `:OUTPut:LOAD INFinity` and
> "was working because the default load is High-Z" is **WRONG**. On this DG902 Pro `INFinity`
> mis-parses to a **1 Ω** load, which over-drove every pin to ~10 V. Several §11.7 negatives
> (esp. the burst tests) were therefore run at the wrong voltage or with **no clock at all**.
> Treat §11.7's burst results as **void**; the continuous-clock crosstalk *ratios* still hold.

### 11.8 Bench session 2026-07-25 — instrument bug found; VDD hypothesis falsified (continuous)

Resumed with the rig wired for the VDD test: AWG **CH1→1 kΩ→pin 2** (clock), **CH2→870 Ω→pin 1**
(DC VDD), 10 kΩ pull-down pin 3→GND, scope CH1–4 on pins 1/2/3 + AWG CH1 out, all grounds pin 4.

**The big find — AWG was over-driving every pin ~3× all along (`scpi_lib.set_highz`):**
- `:OUTPut:LOAD INFinity` on this DG902 Pro **silently sets a 1 Ω load** (readback `1.0`), NOT
  High-Z. Into 1 Ω the AWG clamps commanded amplitude to `~10 V ÷ 51 ≈ 0.196 V` and drives its
  full **~10 V open-circuit EMF** into the high-Z pins. So a "3 V" clock was really **>9.5 V**
  at the pin (clipping the scope at every vertical scale) — ~3× over the 3 V battery ceiling.
- The **only** spelling that gives true High-Z is **`:OUTPut:LOAD INF`** (readback `9.9E37`).
  `10000` = the 10 kΩ max (near-High-Z, ~0.5 % high); `50` and numeric `9.9E37` also mis-parse.
- **Fixed:** `set_highz()` now sends `INF` **and reads it back, raising if not confirmed** — the
  tooling refuses to drive unless High-Z is verified. Detection was query-only (watch whether the
  commanded amplitude gets clamped), so the fix was found without ever driving 10 V again.

**Two more tooling bugs fixed (both masked results):**
- **VDD readback** used an edge trigger through 0 V — a flat DC rail has no edge, so it never
  triggered and returned a stale **0.000 V** (the earlier "pin 1 SAGGING under load!" was a pure
  artifact). Now `Scope.measure_vavg()` reads DC via `:MEASure`/AUTO sweep. Verified: pin 1
  tracks the command 1:1 (1.0→0.99 V, 3.0→3.00 V), **no doubling**.
- **Capture trigger**: added `sweep=AUTO` to `arm_single` + a **"clock actually present on the
  driven pin" guard** in `vdd_burst_capture.py`, so a missing/one-shot clock can no longer
  masquerade as a "no response."

**Results with the corrected 3 V clock:**
1. **VDD (3.0 V, steady) on pin 1 + continuous 9 kHz on pin 2 → pin 3 = 0.74 V** vs a clock of
   3.17 V, i.e. ratio **0.23 ≈ the 0.21 crosstalk coupling factor.** **Clean negative:** powering
   pin 1 does **not** wake the data line (for a continuous clock). VDD held 2.997 V — *no* sag,
   which is expected for a healthy CMOS input (nA quiescent), so "no sag" neither confirms nor
   denies pin1=VDD; the pin-3 response is the real test, and it stayed crosstalk.
2. **Burst mode never actually fired a clock** — the guard caught pin 2 at 0.08 V, 0 transitions.
   `:TRIGger1:SOURce IMMediate` is a one-shot, not an auto-repeat. **⇒ Burst framing — the
   mechanism real iGaging readers use — has NEVER been delivered to the mic** (this session or
   §11.7). It is the strongest *untested* lead.

**Burst train — finally delivered, and the DATA button — retested (later same session):**
- **Burst SCPI resolved by scope-measuring the AWG output.** `:SOURce1:BURSt:TRIGger:SOURce` is
  `-113` on this firmware; the auto-repeat source is the ORIGINAL `:TRIGger1:SOURce IMMediate`
  (re-fires the N-cycle burst every `:BURSt:INTernal:PERiod`; scope-confirmed pin VPP≈3.3 V,
  VAVG consistent with a 21-cyc/10 ms train). The burst IDLES HIGH (no working idle-level cmd —
  all `-113`); **`:OUTPut1:POLarity INVerted`** flips it to a clean **idle-LOW** train (pin2
  VAVG 2.6→0.41 V, verified). A second capture bug also fixed: digitising ONE `read_raw` window
  can miss a burst (RAW memory time-span < the 10 ms period → lands in the idle gap); the
  decision now uses live `:MEASure` (`Scope.measure_item`), which re-evaluates every sweep.
- **VDD + burst, idle HIGH → pin3 VPP 0.77 V, symmetric ±0.36 (crosstalk).** Negative.
- **VDD + burst, idle LOW → pin3 VPP 0.75 V, symmetric ±0.36 (crosstalk).** Negative.
- **DATA button retested with working tooling** (`button_data_capture.py`, then a 40 s live
  monitor): VDD on pin1, continuous 3 V clock on pin2, button mashed. A NORMal trigger armed at
  +1.0 V on pin3 fired **once** (a mechanical/EMI press glitch — RAW readback was flat), but the
  40 s / **741-sample** monitor showed pin3 never left ±0.42 V. **The DATA button does NOT gate
  or drive the data line.** Matches the research (it's the factory cable's PC-keyboard trigger).

**Two final no-rewire checks — both negative:**
- **Slow-clock sweep** (VDD on pin1, continuous clock on pin2, 200 Hz–9 kHz): pin3 stayed
  symmetric ±0.36 V at every frequency, pin3/clk ratio ~0.22 throughout. No slow-clock response.
- **Pure-passive button** (AWG OFF, monitor all 3 pins 40 s while pressing DATA): every pin sat
  at floating noise (pin1 ±0.2, pin2 ±0.15, pin3 ±0.1 V). **No self-clocked frame.** Confirms
  the DATA button does nothing observable on the connector.

**State after today (revised):** CLK/DATA still unconfirmed. Ruled out AT CORRECT VOLTAGE, on
the assumed pin2=CLK/pin3=DATA mapping: continuous clock (all pins); VDD + continuous; VDD +
burst (idle high AND low); VDD + continuous + DATA-button; slow clock 200 Hz–9 kHz; passive
button (self-clock). The mic drives **nothing** on any pin under every stimulus we can produce —
**the entire no-rewire stimulus space is exhausted.** The one unverified assumption left is
**which pin is CLK vs DATA vs VDD** (only physical order 1-2-3 and "all float at idle" were ever
confirmed; the role mapping came from generic iGaging research, not this unit). **Next: the
pin-permutation sweep** — drive each pin as clock and each other as VDD in turn, watching the
rest for a rail-clamped (driven) response. Needs rewiring between combos.

### 11.9 Pin-permutation sweep — ALL 6 combos negative (2026-07-25 cont.)

Drove each pin as clock and each other as VDD in turn (`pin_sweep.py`, continuous 9 kHz, 3 V,
VDD 3 V), watching the third for a rail-clamped (driven) vs symmetric (coupling) response:

| clk | vdd | watch | watched-pin verdict |
|-----|-----|-------|---------------------|
|  1  |  2  |   3   | coupling |
|  1  |  3  |   2   | coupling |
|  2  |  1  |   3   | coupling (from §11.8 runs) |
|  2  |  3  |   1   | coupling |
|  3  |  1  |   2   | coupling |
|  3  |  2  |   1   | coupling |

**The mic drives NOTHING on any pin under any CLK/VDD/DATA role assignment.** CLK/DATA identity
is moot — no pin ever actively drives; every watched pin shows only symmetric-about-0 coupling
that scales with the clock. VDD (3 V) held rock-steady on whichever pin supplied it (healthy
CMOS-input behaviour, ~nA draw).

**Two instrument gotchas caught mid-sweep:**
- **Scope CH2 probe 1×/10× switch bumped to 10×** while software stayed 1× → CH2 read every
  voltage 10× LOW, faking a VDD "sag" on pin2 (multimeter confirmed pin2 = 2.998 V while the
  scope showed 0.30 V). Fixed by restoring the probe switch to 1×. **Lesson: re-verify probe
  attenuation after handling.** `pin_sweep` now aborts if supplied VDD doesn't read back ≥80% of
  commanded (catches a dead VDD path / probe mis-scale). No data was missed — every watched-pin
  verdict was symmetric coupling regardless of scale.
- `:MEASure VTOP/VBASe` return the 9.9E37 "not ready" sentinel on a pure-coupling line (no clear
  bimodal high/low); `pin_sweep` uses VMAX/VMIN (raw peak/trough) for the shape check.

**BOTTOM LINE after 2026-07-25:** external clock injection on ANY pin, in ANY role (clk/data/
vdd), continuous OR burst (assumed mapping), fast OR slow (0.2–9 kHz), with/without VDD,
with/without the DATA button, actively pressed or passive — produces **ONLY passive crosstalk.**
The mic never actively drives a connector pin. Still genuinely untested: **burst-mode
permutations** (all 6); **clocking while the spindle MOVES** (data-on-change encoders only emit
on movement — every test so far was on a STATIC reading); or the port requires the genuine host
handshake (official `100-700-USB-MC` cable) we haven't reproduced.

### 11.10 Recommended next steps (ranked by value ÷ effort)

Injection is exhausted; these are what remains, in the order worth trying.

1. **Clock/listen while the spindle MOVES — DO THIS FIRST (cheap, no rewiring).** Every test to
   date was on a *static* reading. Some encoder ASICs only shift out (or only self-clock) when
   the position changes. Two variants on the current wiring:
   - *Passive + motion:* AWG off, monitor all three pins (like `passive_button_monitor`) while
     slowly turning the spindle — catches a self-clocked "on-change" output.
   - *Clocked + motion:* drive the clock on a pin (VDD on another) and watch the third while
     moving the spindle — catches an output that only updates on movement.
   If any pin swings a real (rail-clamped) level, injection is back on and we go to Phase B.

2. **Burst-mode permutation sweep (all 6 combos)** — completes the matrix (`pin_sweep --mode
   burst` per combo). Low expected value: the continuous permutations were all dead and burst on
   the assumed mapping was dead, but it's the last stone unturned in pure injection. Needs the
   same 6 rewires as §11.9.

3. **Step back to the genuine host interface.** It is a real possibility that THIS unit's port
   needs the official cable's handshake (an init/bias/enable) or simply isn't the generic 21-bit
   protocol on this model. Options: obtain the iGaging **`100-700-USB-MC`** cable and sniff its
   lines with the scope (definitive — shows exactly what the host does), or conclude that
   passive/injection RE has hit its limit on this unit.

Instrument state carried forward (all verified this session): AWG raw-SCPI **:5025**; **High-Z =
`:OUTPut:LOAD INF`** (never `INFinity`); DHO814 timebase `:TIMebase:MODE MAIN`; use `:MEASure`
(`Scope.measure_item`) not RAW-window digitising for bursty signals; VMAX/VMIN not VTOP/VBASe on
coupling-only lines; **re-check probe 1×/10× switches after handling.** Tools ready to reuse:
`pin_sweep.py`, `vdd_burst_capture.py`, `button_data_capture.py`, `scpi_lib.py`.

### 11.11 Board teardown (2026-07-25/26) — the OPEN-COLLECTOR hypothesis

> ## ⚠ STANDING CONSTRAINT arising from this teardown
>
> **1. Do not re-open the mic except as a last resort, and then only once.** The FPC retaining-clip
> tabs broke here; the tape/glue repair **will not tolerate much strain**, so another opening risks
> taking the unit out of service. Exhaust every experiment doable through the Micro-USB breakout
> (case closed) first, then batch *all* board work into a single planned session with a written
> checklist, and reinforce the FPC while it is open. Checklist: `review.md` §5.1.
>
> **2. Only the battery side has ever been observed.** The MCU is an unreachable COB blob on the
> LCD side. So the topology described below — "MCU-GPIO → 330 kΩ → NPN base, collector = output
> pin" — is a **plausible reading of the visible components, not a traced circuit**. The same
> applies to the assumption that pins 2/3 land directly on MCU inputs rather than being routed or
> gated on the hidden side, and to the assumption that no further components exist there. The
> hidden side has never been photographed. Wherever this topology is used as an argument, it is
> supporting inference; load-bearing conclusions need empirical backing. See `review.md` §5.1a.

With injection exhausted, opened the housing for photos (in `board_teardown/`). **Could not reach
the MCU side** — the LCD is soldered to the board and the board/LCD assembly is glued into the
front cover; separating it needs enough force to crack the glass, so it was left intact (only a
~1 mm gap, no borescope access). In the process the **read-head FPC retaining-clip tabs cracked
off** — the flex must be re-secured (reseat + Kapton tape / dab of glue, keep adhesive off the
contacts) before the mic is trusted again.

**What the accessible (battery) side shows** (`board_teardown/PICT0011,0022,0023,0028,0037.jpg`):
- Board silkscreen **`MD311-4.1A`**.
- A **jumper-configuration matrix** `J10–J81` (pad pairs) → this is a **multi-mode board**; bridged
  jumpers select which signals route to which Micro-USB pins. Different iGaging SKUs share it.
- **Q1, Q2 = SOT-23 marked `1AM` = MMBT3904 NPN**, each fed by a **330 kΩ base resistor**
  (R1, R2 = "334"; also a "473" = 47 kΩ). MCU-GPIO → 330 k → NPN base, collector = output pin,
  emitter = GND: **textbook open-collector output drivers.**
- 5-pin **Micro-USB**, 6-pin read-head **FPC**, CR2032. The **MCU is a chip-on-board blob on the
  hidden LCD side** — no part number obtainable.

**THE HYPOTHESIS (explains every negative to date):** the data-port CLK/DATA are **open-collector**
— they can only pull the line **LOW** and float (high-Z) otherwise, so they require an **external
pull-UP** to ever read HIGH. This matches the measured "all pins float at idle, no internal
pull-ups." **Every test we ran used a pull-DOWN (to kill crosstalk) or no pull-up at all — which
MASKS an open-collector output** (the line sits at ground regardless of the transistor), so the
mic pulling DATA low for bits produced no visible change. It also undermines the "host-clocked"
conclusion (§11.4): that came from *passive* listening **without pull-ups**, which likewise can't
see OC outputs — so the mic may actually be **device-as-master** (self-clocked, Digimatic-style,
two OC drivers = clock + data).

**NEXT TEST PLAN — pull-UPs, not pull-downs (tooling written, ready to run):**
- **+3 V rail from the B&K 169x bench supply** (`psu_lib.py`; 3.00 V, **20 mA current limit**,
  OVP 3.6 V; **−** → pin 4). Bench supply chosen over the AWG for the settable current-limit
  safety net, cleaner DC, and to keep the AWG free for the clock. Pull each signal pin UP via
  **~10 kΩ**.
- **TEST 1 — passive (`pullup_passive_monitor.py`):** pull all 3 pins to 3 V, inject nothing,
  watch for any pin dipping off the rail while pressing DATA / turning the spindle (device-as-
  master / self-clocked OC). If a pin dips, `--capture-pin N` grabs the frame on a falling edge.
- **TEST 2 — clocked (`pullup_clock_capture.py`):** if Test 1 is quiet, drive the clock on the
  CLK pin with DATA pulled UP, watch DATA dip low for bits (host-clocked OC). Rotate clk/data
  pins / try `--mode burst` as needed.
- The **spindle-MOTION** variable (§11.10 #1) folds into both: press DATA *and* move the spindle
  during the window, in case the output only updates on change.

If pull-ups finally reveal a driven line → Phase B (framing/bit-order/sign) via
`analyze_capture.py`. If even pull-ups are silent, the remaining option is sniffing the genuine
`100-700-USB-MC` host cable (§11.10 #3).

### 11.12 Pull-up / open-collector tests — negative; injection EXHAUSTED (2026-07-26)

> ## ⚠ RETRACTED — this section's central conclusion is a FALSE NEGATIVE
>
> **"The mic never actively drives any connector pin" is wrong.** §11.14/§11.15 — later the same
> day — showed that a clock on pin 2 *or* pin 3 with the DATA button held makes **pin 1 drive
> low**. That is *exactly* the Test 2 configuration below. Test 2 should have caught it.
>
> **Why it didn't** (diagnosed in `review.md` §1.3, not at the time): the monitoring method, not
> the stimulus. `pullup_clock_capture.py` polls `:MEASure:ITEM? VMIN` in a Python loop over a
> **4 ms** acquisition window; `pullup_passive_monitor.py` uses **10 ms** and logged 466 samples
> in 40 s (~11.6 queries/s). Effective observation coverage is **~4–12 % of wall-clock time**. A
> ~25 ms strobe firing once per button press is present ~2.5 % of the time, so the expected number
> of detections in a 40 s run is well under one. **A null from this monitor is not evidence of
> absence.** Every "monitored N seconds, no dip" result in §11.8, §11.10 and this section is
> **inconclusive, not negative.**
>
> Note also that §11.14's explanation — that the DATA button was "the one interaction we'd never
> combined with the pull-up rig" — is contradicted by this section's own text: the button *was*
> pressed in both tests here.
>
> **Two further defects** found by audit:
> - **All the capture files from Test 2 are 0 bytes** (`pullup_clk_cont_p{1,2,3}_ch*.bin`,
>   `pullup_clk_burst_p1_ch*.bin`). Cause: `read_raw()` is called while the scope is still in
>   `:RUN`; Rigol RAW readback needs `:STOP` first. The verdicts below came from live `:MEASure`
>   only — there is no waveform artifact to re-examine.
> - The pull-ups used were **10 kΩ**. The reference implementations specify **~100 kΩ**, and
>   Q1/Q2's 330 kΩ base resistors cap the sink current at ≈0.7 mA against the 0.3 mA a 10 kΩ
>   pull-up demands — roughly 2× margin. A weakly-driven pin could have been held near the rail.
>
> The "0.0 mA on pin 1" reasoning is also unsound as stated — see the inline note below.

Acted on the §11.11 open-collector hypothesis: supply a +3 V rail from the B&K 169x bench supply
(`psu_lib.py`) and pull the signal pins UP (never down), so an open-collector output — which can
only pull LOW — becomes visible. Mic alive and reading correctly throughout (FPC re-secured).

- **TEST 1 — passive, all 3 pins pulled up** (`pullup_passive_monitor.py`), nothing injected,
  pressing DATA + turning the spindle: every pin held at the 3 V rail, 0/466 samples dipped.
  **No self-clocked OC output** → not device-as-master.
- **TEST 2 — clock injected + pull-ups** (`pullup_clock_capture.py`, monitored 40 s while
  pressing DATA + moving the spindle): clock on **each** of pins 1/2/3 in turn (the other two
  pulled up and watched), **continuous** for all three and **burst** on pin 1 — every watched pin
  stayed at the rail (VMIN floors ~2.6 V; a real OC bit would hit ~0.2 V). **No driven DATA.**
- **Solid-VDD combination** (the one setup never tried: pin 1 wired DIRECTLY to +3 V = solid VDD,
  clock on pin 2, pull-UP on pin 3 = DATA, watch pin 3): DATA held at the rail — **negative.**
  Crucially, **pin 1 drew 0.0 mA** from the supply and nothing changed → **pin 1 is NOT a VDD
  input that powers the interface** — ⚠ *the inference is unsound: the same supply also sources
  three 10 kΩ pull-ups (~0.9 mA), so the B&K's display resolution puts a floor under this reading,
  and §11.8 correctly noted that a healthy CMOS input draws ~nA either way. "0.0 mA" cannot retire
  the hypothesis. (§11.15 does retire it, properly: pin 1 is an output.)* — (retires the
  "unpowered interface" hypothesis from §11.7/11.11;
  the data interface is internally powered from the CR2032, and pin 1 is just another signal/OC
  pin). pin 1's apparent ±2 V swing was a **VMAX/VMIN peak-detector NOISE artifact** — with the
  clock off, pin 1 VAVG was a rock-solid 3.013 V (connection good) while VMAX/VMIN still showed
  4.29/1.79 from EMI peaks. **Lesson: trust VAVG for a DC level; VMAX/VMIN exaggerate noise.**

**CONCLUSION — external stimulation is exhausted.** With the mic reading correctly, and with
pull-ups in place so open-collector outputs *would* be visible: clock on every pin (continuous +
burst), power/VDD on the pins (0 mA draw, no effect), DATA button pressed, spindle moving — **the
mic never actively drives any connector pin.** This is a comprehensive negative, not a
pin-identification gap. (Not literally every permutation was run — e.g. solid-VDD was only tried
on pin 1, burst only on some clock positions — but the 0 mA VDD draw and the uniform silence make
further permutations very low value.)

**DEFINITIVE NEXT STEP — sniff the genuine host cable.** Obtain the official iGaging
**`100-700-USB-MC`** cable, plug it into this mic, and scope its lines while it reads. That
captures the real host behaviour we cannot reverse-guess: the exact clock pattern, the true pin
roles, and any **init / wake / handshake** the cable's MCU performs (the most likely reason every
open-loop stimulus is ignored). Once the real protocol is captured → Phase B decode → build our
own ESP32 front-end. Absent the cable, passive + injection RE has reached its limit on this unit.

New tooling this session: `psu_lib.py` (B&K 169x client), `pullup_passive_monitor.py`,
`pullup_clock_capture.py` (both drive the PSU and force-off on exit).

### 11.13 NEW hypothesis — Mitutoyo Digimatic-style SPC (REQ-triggered, DEVICE-clocked)

> ## ⚠ STILL OPEN — arguably the leading hypothesis. No results were ever recorded here.
>
> **No results were ever recorded for this section.** `req_capture.py` was run (artifacts:
> `req_p1_scope.png`, `req_p2_frame_*`, `req_p3_frame_*`, `req_p3_scr_*`) but the outcome was
> never written up. §11.15 cites this section as an established negative; that citation has no
> supporting text here. **That gap is still the main problem with this section.**
>
> **Correction to an earlier banner.** A previous revision of this note claimed the hypothesis was
> "largely closed" because the documented micro-B mapping puts REQ on pin 4 (ID) and §11.3 measured
> pin 4 hard-grounded. **That was wrong and is retracted.** The pin-4 assignment comes from
> `igaging_protcol_research.md`'s *generic* iGaging mapping — the same mapping that is already
> falsified on this unit (it says pin 1 = VDD and pin 3 = tool-driven DATA; both wrong here). A
> discredited mapping cannot rule out a protocol. See `review.md` §10.3.
>
> **Our own data fits Digimatic well:**
> - **Pin count is exact.** Digimatic minimally needs REQ + CLK + DATA + GND. This unit has three
>   signal pins and two grounds, and needs no VDD pin — it is self-powered (pin 1 drew 0.0 mA,
>   §11.12). REQ simply is not on pin 4; with pin 1 not being VDD, the generic mapping shifts.
> - **It resolves the Q1/Q2 puzzle** raised below: two open-collector drivers but only one
>   identified output pin is exactly what Digimatic predicts — Q1 and Q2 = the device's CK + DATA.
>
> **Against it:** §11.15 measured one output and two inputs, where Digimatic wants two outputs and
> one input. That is the real counter-evidence — but it is softer than it reads (driving a pin
> masks device drive on it, only 2 of 4 unmasked cells were captured, and the 10 kΩ pull-ups are
> within ~2× of what these weak drivers can sink). See `review.md` §3.4, §5.7a.
>
> **Note on `igaging_dataconnect_hardware_findings.md`:** it argues for Digimatic from the
> accessory hardware, but it is unmeasured desk research written with no knowledge of this project.
> It is not why this hypothesis is open — our own pin count is. Its one actionable contribution is
> to ohm out the adapter cable if it is ever bought (`review.md` §11.2).

Before buying the adapter, one signaling **direction** we never tried. Prompted by an observation
about iGaging's two adapters:

- **`100-700-USB`** (SPC): control box with USB out + a **10-pin box-header input**, ships with a
  cable that has a **Mitutoyo-style "Type C" Digimatic SPC** connector on the tool end and the
  10-pin box plug on the other.
- **`100-700-USB-MC`** (this mic's adapter): control box looks **visually identical**, ships with a
  cable that has a **Micro-USB** tool end and the **same 10-pin box plug**.

**Caveat (do not overstate):** we have NOT established the two control boxes are electrically
identical — only that they look alike and their cables share the same box-end (10-pin) connector.
The box could auto-detect, or the two cables could map signals differently. So "the Micro-USB port
is Digimatic" is a **hypothesis**, not a fact.

**But the REQ / device-clocked model is independently supported by our own evidence**, regardless
of the cable inference. **Mitutoyo Digimatic SPC works opposite to the "host-clocked" premise we
assumed all along:**

| | Assumed (host-clocked) | Digimatic SPC |
|---|---|---|
| Clock source | **we** generate it | **the device** generates it |
| Trigger | none / continuous | host asserts **REQ** (active-low) |
| Data | device shifts on our clock | device clocks out ~52 bits (13 BCD nibbles) after REQ |

The reader holds **pull-ups** on DATA/CK/REQ; the host pulls **REQ low**; the device then drives
**both CK and DATA** (open-drain). This explains **every** prior negative:
- Passive, even WITH pull-ups (§11.12 Test 1): no REQ asserted → device never transmits → silence.
- Clock injection on every pin (§11.9–11.12): wrong direction — the device owns the clock.
- Board has **two open-collector drivers** (Q1/Q2, §11.11) = the device's **CK + DATA** outputs
  (a host-clocked slave wouldn't need two OC drivers).
- Solid "VDD" on pin 1 drew **0.0 mA** (§11.12) → pins 1/2/3 are **signals**, not power.

Also corrects the §11.4/§11.7 "21-bit host-clocked" premise, which likely conflated the raw
capacitive-scale 2-wire interface (host-clocked, used by TouchDRO-style readers directly on the
encoder) with the **SPC output** on this connector.

**Test (`req_capture.py`):** pull **all three** signal pins UP to +3 V; drive ONE pin active-LOW
(REQ) at ~20 Hz; watch the other two for the **device** pulling them low (its self-generated
CK + DATA). Try each pin as REQ; slow the REQ rate (5–10 Hz) if needed to give the device more
time low. `--capture` arms a falling-edge trigger on a watched pin to grab the actual device frame
→ then Phase B decode. Wiring: PSU +3 V → 10 kΩ → each of pins 1/2/3; AWG → 1 kΩ → the REQ pin;
grounds → pin 4. **If this reveals device-clocked data, injection RE succeeds with no adapter
needed;** if silent across all three REQ pins + rates, the §11.12 conclusion stands (sniff the
real cable).

### 11.14 BREAKTHROUGH — the DATA button triggers a device response (2026-07-26)

> ## ⚠⚠ SUPERSEDED — pin 1 is the DATA BUTTON'S SWITCH CONTACT, not a device output (§11.19)
>
> **The mic never drove anything.** With the **battery OUT**, the DMM's continuity buzzer sounds
> for exactly as long as the DATA button is held — so pin 1 conducts to ground *unpowered*, which
> a transistor cannot do. Pin 1 is a mechanical switch to ground, brought out to the connector for
> the host cable's benefit.
>
> Everything in §11.14–§11.18 about pin 1 is therefore **characterisation of a pushbutton**, not of
> a device response. The measurements are all still valid; the interpretation is not.
> The title is wrong: there was no device response. Pressing the button closed a switch.


**After two-plus sessions of total silence, the mic finally drives a connector pin.** The
trigger was the on-body **DATA button** — ~~the one interaction we'd never combined with the
pull-up rig~~.

> **⚠ That attribution is wrong.** The button *was* combined with the pull-up rig — §11.12 Tests 1
> and 2 both say "pressing DATA" explicitly, and Test 2's clock-on-pin-2/pin-3 runs are the very
> configuration §11.15 shows works. What was new here was not the button; it was **catching** the
> response. §11.12 monitored by polling `VMIN` over a 4–10 ms window at ~11 queries/s (~4–12 %
> observation coverage) and missed a ~25 ms event, whereas this session armed a real trigger. See
> the §11.12 banner and `review.md` §1.3.

**Setup:** all three signal pins pulled UP to +3 V (bench PSU); AWG pulsing pin 3 at ~10–20 Hz
active-low ("REQ", via 1 kΩ); scope watching pins 1 & 2; mic awake, reading. Then **press the
DATA button.**

**Result:** **pin 1 is actively driven LOW — hard, to ~−0.7 V (open-collector)** — in bursts that
track each button press (`findings/2026-07-26_databutton_*.png`). This is the FIRST active drive
we've ever seen. Neither passive-pull-ups-with-button (§11.12 Test 1) nor REQ-without-button
produced it; it needs **the button** (with pin 3 being driven — whether pin 3's pulsing is
*required* or incidental is not yet nailed down).

**Partial characterization (decode NOT yet complete):**
- **pin 1 = the hard-driven line** (open-collector to −0.7 V). pin 2 / pin 3 show only weak
  signal / noise, not hard-driven.
- High-res RAW (3.2 ns/pt): pin 1 makes **one clean high→low edge and stays low ≥1.6 ms** — no
  fast bit-toggling in that capture. The earlier wide (20 ms) screenshot showed **dense burst
  activity spanning ~10 ms**. So the full event is long and may have structure our captures
  haven't cleanly resolved — pin 1 is either DATA or a driven strobe; **framing/bit-rate/CLK
  location still unknown.**

**Instrument gotchas (decode blockers to fix next):**
- **DHO814 RAW multi-channel readback is INCONSISTENT** — the same frozen capture read back as
  10 k / 250 k / 1 M points on different calls, and a 2nd channel read sometimes returns short.
  **NORMal (on-screen, ~1000-pt) read is reliable** but low-res. `req_capture --capture` also
  read the memory **too soon after the trigger** (needs a settle delay). Use NORMal or add
  settle + verify point count.
- The bits (if any) are **faster than the 1000-pt screen read resolves** at a 2 ms window — a
  decode capture needs a window/depth matched to the (still-unknown) bit rate with a reliable
  readout.

**NEXT — clean decode campaign:** (1) determine the **minimal trigger** (button alone vs button +
pin-3 drive); (2) capture the **whole ~10 ms event** at high resolution with a *reliable* readout
(NORMal-mode tiling, or fixed RAW read + settle); (3) identify **CLK vs DATA** and decode framing
→ Phase B. Tooling: `req_capture.py` (`--capture`, `--cap-tb-us`, byte-range debug);
`findings/` holds the milestone screenshots.

### 11.15 Clock-sweep WITH the button — pin roles nailed down (2026-07-26)

> ## ⚠⚠ SUPERSEDED — pin 1 is the DATA BUTTON'S SWITCH CONTACT, not a device output (§11.19)
>
> **The mic never drove anything.** With the **battery OUT**, the DMM's continuity buzzer sounds
> for exactly as long as the DATA button is held — so pin 1 conducts to ground *unpowered*, which
> a transistor cannot do. Pin 1 is a mechanical switch to ground, brought out to the connector for
> the host cable's benefit.
>
> Everything in §11.14–§11.18 about pin 1 is therefore **characterisation of a pushbutton**, not of
> a device response. The measurements are all still valid; the interpretation is not.
> "pin 1 = the mic's sole OUTPUT" is wrong in kind. Driving pin 1 did nothing because you
> were fighting a closed switch. **Pins 2 and 3 remain the only real interface.**


> ## ⚠ PARTLY RETRACTED — the trigger condition below is wrong (see §11.18)
>
> **"Both are required" is false. The DATA button ALONE triggers pin 1's strobe** — no clock, no
> input edges. Confirmed 3/3 by direct capture with the AWG switched off (§11.18). The clock in
> the table below was **incidental, not causal**.
>
> The error came from citing §11.12's button-alone result as an established negative. That run's
> detection was the VMIN polling loop covering ~4–12 % of wall-clock time, so its null was never
> evidence of absence — the third false negative from that same defect (`review.md` §1.3).
>
> **What still stands:** pin 1 is the mic's output and driving pin 1 itself does nothing; pins 2
> and 3 are inputs. **What does not:** that input edges are required to trigger anything, and
> the "−0.7 V" figure for pin 1's low, which §11.18 measures as ~−0.03 V (ground).

Prompted by "have we clocked the *other* pins with the button?" — we'd only ever added the button
to the pin-3 drive. Swept all three clock positions with all pins pulled up + the DATA button
pressed, ~10 Hz AWG square on the driven pin:

| AWG drives + button | Result |
|---|---|
| **pin 2** | **pin 1 driven LOW (−0.7 V)** |
| **pin 3** | **pin 1 driven LOW (−0.7 V)** |
| **pin 1** | nothing (pin 2 & pin 3 stay at the rail) |

**PIN ROLES (this unit, Micro-USB connector):** **pin 1 = the mic's sole OUTPUT** (data / strobe);
**pin 2 and pin 3 = INPUTS** — driving *either* one (with the button) makes the mic assert pin 1;
driving pin 1 itself does nothing. The trigger for the pin-1 response is **(DATA button held) AND
(edges on pin 2 or pin 3)** — both are required (button-alone §11.12 and drive-alone §11.13 each do
nothing). Reliable NORMal-mode readout (added `Scope.read_screen`, + a settle after the trigger)
confirmed pin 1's response is a **long ~10 ms low strobe, independent of clock rate (10 Hz–2 kHz)** —
a "data-ready", not clocked bits; the measurement doesn't shift out from a continuous clock on a
single input.

**MOST PROMISING UNTESTED AVENUE:** we've only ever driven **one input at a time.** A real reader
almost certainly drives **both** pin 2 and pin 3 in a coordinated handshake (one = CLK, the other =
REQ / direction / gate). The DG902 has a **second channel** — next session: drive pin 2 and pin 3
**together** (sweep CLK/REQ role assignments and phase) with the button, and watch pin 1 for
shifted DATA. Also test whether pin 1's pattern tracks the **spindle reading** (→ it's DATA) vs is
fixed (→ pure strobe). If coordinated 2-input driving still yields no bits, the `100-700-USB-MC`
cable sniff is the definitive decode reference.

### 11.16 Two-input handshake — exhausted; blind decode is at its limit (2026-07-26)

> ## ⚠⚠ SUPERSEDED — pin 1 is the DATA BUTTON'S SWITCH CONTACT, not a device output (§11.19)
>
> **The mic never drove anything.** With the **battery OUT**, the DMM's continuity buzzer sounds
> for exactly as long as the DATA button is held — so pin 1 conducts to ground *unpowered*, which
> a transistor cannot do. Pin 1 is a mechanical switch to ground, brought out to the connector for
> the host cable's benefit.
>
> Everything in §11.14–§11.18 about pin 1 is therefore **characterisation of a pushbutton**, not of
> a device response. The measurements are all still valid; the interpretation is not.
> "pin 1 carries no measurement information" was the right conclusion for the wrong reason —
> it is a button. The reading-independence follows trivially.


Drove BOTH inputs together (`two_input_capture.py`: AWG CH1 = CLK square on one input, CH2 = REQ
DC-held on the other) + DATA button, watching pin 1:

| CLK | REQ | REQ level | pin 1 result |
|-----|-----|-----------|--------------|
| pin 2 | pin 3 | low (0 V)  | strobe only (1 transition) |
| pin 2 | pin 3 | high (3 V) | strobe only |
| pin 3 | pin 2 | low (0 V)  | strobe only |

**pin 1 never shifts data** — across single-input, dual-input, either REQ polarity, either role
assignment (pin 2/pin 3 are symmetric inputs), continuous clock **10 Hz through 9 kHz**. It is
always the same clean ~10 ms "data-ready" low, and no serial measurement data appears on any pin.

**9 kHz specifically checked** (iGaging's documented native clock rate): single-input clocking
pin 2 at 9 kHz, single-input clocking pin 3 at 9 kHz, and two-input (CLK pin 3 @ 9 kHz / REQ pin 2)
— **all still just the strobe.** So the clock *rate* is confirmed NOT the missing factor; pin 1's
response is rate-independent.

**Reading-dependence checked (~~decisive~~ — see correction):** captured pin 1's strobe at
**0.065 mm** vs **24.698 mm** (wildly different readings), 50 ms window, same button tap. ~~The two
pin-1 waveforms are **byte-for-byte IDENTICAL** (0/1000 samples differ; both a ~25 ms low, 1
edge).~~ **pin 1 carries no measurement information — it is a pure fixed "data-ready" strobe**, not
the data. This conclusively rules out the last hypothesis that pin 1 might itself encode the value
(e.g., pulse-width/timing).

> ## ⚠ CORRECTION — "byte-for-byte identical" is false, and the test cannot support "conclusively"
>
> Re-analysis of the stored captures (`review.md` §1.1):
>
> | Comparison of `readingA_ch1` vs `readingB_ch1` | Result |
> |---|---|
> | Raw bytes differing | **931 / 1000** |
> | Digitised at a 1.5 V threshold | 0 / 1000 |
> | Digitised at a 0.5 V threshold | **155 / 1000** (121 vs 125 transitions) |
> | Post-trigger V<sub>avg</sub> | −0.02 V (both) — **not** the "−0.7 V hard low" of §11.14 |
> | Post-trigger RMS, 2.5 ms bins, A | 0.72 0.33 0.28 0.62 0.54 0.33 0.50 0.66 0.27 |
> | Post-trigger RMS, 2.5 ms bins, B | 0.32 0.51 0.64 0.27 0.29 0.73 0.30 0.35 0.62 |
>
> The records are identical **only after being crushed to one bit at a 1.5 V threshold.** The
> post-trigger region carries a time-varying ±0.7 V envelope whose bin-by-bin pattern **differs
> between the two readings** and was never analysed.
>
> **That envelope has since been identified as clock crosstalk, not data** (checked 2026-07-26):
> at a 0 V threshold pin 1 toggles at 7.41 kHz in `readingB` against an 8.40 kHz injected clock,
> and 7.45 kHz in `readingA_clk2` against 8.48 kHz — ratios of 0.883 and 0.879 across two runs that
> used **different clock pins**. Tracking the injected clock like that is crosstalk, undersampled
> (an ~8.4 kHz signal at 20 kSa/s aliases exactly this way), not device data. The conclusion above
> is unaffected; this particular loose end is closed. *One oddity remains: ~1.4 Vpp of crosstalk on
> a pin supposedly hard-driven low by a saturated NPN, which should have swamped it — further
> support for the weak-driver concern in `review.md` §5.7a.*
>
> **Two further limits on what this test could show:**
> - **Resolution.** `xinc = 5.0E-5` → **50 µs/sample**, 1000 points. Against the documented 9 kHz
>   clock (111 µs bit period) that is ~2.2 samples/bit, with nothing to spare. Anything faster is
>   invisible. §11.14 said exactly this ("the bits, if any, are faster than the 1000-pt screen read
>   resolves") two sections earlier.
> - **The "~25 ms low" is a trigger artifact.** The low region is samples 501–999 — it begins at
>   the trigger point (centre screen, offset 0) and **runs to the end of the record.** The pin is
>   still low when acquisition stops. Same for §11.14's "stays low ≥1.6 ms" (half of a 3.2 ms
>   window). **The end of the pin-1 event has never been observed**, so its true duration is
>   unknown — and "~10 ms" (§11.14), "~10 ms" (§11.15) and "~25 ms" here are three inconsistent
>   figures for the same event.
>
> What survives: pin 1's *coarse 1-bit envelope at 50 µs resolution* is the same at both readings.
> That is worth knowing but is not "conclusively rules out."

**Both INPUT pins also checked unmasked at both readings (closes the "masking" loophole):** when we
drive a pin as the clock we *mask* any data the mic might put on it, so we watched each input
*unmasked* (clock the OTHER input) at 0.065 mm and 24.698 mm. Phase-invariant metric (does the pin
ever get pulled HARD low = real open-collector data, vs the small 2.5–3.4 V crosstalk wiggle):
**pin 2 unmasked → 0 % hard-low at both readings; pin 3 unmasked → 0 % hard-low at both readings.**
Neither input is ever actively driven, and neither changes with the reading. **Conclusion: NO
connector pin (pin 1 output, pin 2/pin 3 inputs) carries the measurement data under any stimulus,
at either reading.** The data is only obtainable via the read handshake — definitively gated on the
cable sniff (task #6).

> **⚠ On "both INPUT pins checked unmasked at both readings":** only two of the four required cells
> have surviving artifacts. `readingA_clk2` covers pin 3 unmasked at reading A (V<sub>min</sub>
> +2.57 V) and `readingB` covers pin 2 unmasked at reading B (+2.48 V) — both genuinely 0 % hard-low.
> But the `readingA` run **saved only channel 1**; its other channels were never written. The
> conclusion is probably right; the document asserts more than the data carries. See also the
> 10 kΩ-vs-100 kΩ pull-up caveat in the §11.12 banner — "not hard low" assumes the pull-up cannot
> overpower the driver, which was never verified.

**CONCLUSION — ~~blind reverse-engineering has reached its limit on this unit~~ (overstated —
see banner below).** The interface is fully
mapped (pin 1 = output/data-ready strobe; pin 2, pin 3 = inputs; trigger = DATA button + edges on an
input), but the mic only shifts the actual reading in response to a specific **timed READ HANDSHAKE**
(what the official cable performs) that can't be reliably guessed. Remaining ideas (precisely
sequenced pulse-REQ-then-burst-CLK, phase-locked dual drive, etc.) are low-odds shots in the dark.

**To finish the decode → sniff the `100-700-USB-MC` cable (task #6):** capture the exact handshake it
performs on these pins, reproduce it, and read pin 1. That turns everything mapped here into a
working DIY ESP32 interface. Alternatively the cable simply works as-is for data capture.

**Session net (2026-07-26):** total silence → a confirmed, working, button-gated interface with
fully identified pin roles. Major progress; the remaining data decode is gated on obtaining the
cable handshake as a reference.

> ## ⚠ "Exhausted" / "reached its limit" is overstated — concrete experiments remain
>
> This is the third section to declare a search space exhausted; the previous two (§11.8, §11.12)
> were each overturned by a later section doing something outside the "exhausted" set. Still
> untried, all cheap and none requiring a purchase (`review.md` §5, `STATUS.md`):
>
> - **Clock duty cycle has never been varied.** The reference 21-bit clock is **20 % duty**
>   (22 µs high / 89 µs low, idle LOW). Every clock this project has produced was **50 %**:
>   `Awg.square()` defaults to `duty=50` and `configure_burst()` never issues `DCYCle` at all, so
>   even the burst trains were symmetric.
> - **Burst on an *input* pin, with pull-ups and the button, has never been run.** Burst-with-
>   pull-ups was only ever driven into **pin 1** — the pin later identified as the *output*.
> - **Clocking gated from pin 1's falling edge** — i.e. treating pin 1 as DRDY and clocking
>   *inside* the low window. Every test so far used a free-running clock asynchronous to the strobe.
> - **The two-input matrix is 3 cells**, and the phase sweep §11.15 proposed was never built
>   (`two_input_capture.py` holds REQ as a DC level and has no phase parameter).
> - **Pull-ups at 100 kΩ**, and at the internal rail voltage — which is *still unmeasured* after
>   two teardowns (open since §10 of the old investigation doc; measure across C4/C5).
> - **Ring out Q1/Q2, the `J10–J81` matrix, and the DATA button contacts** to the connector pins.
>   DMM-only, board already accessible, and it resolves the two-drivers/one-output contradiction.
>
> **Open risk not considered anywhere in this log:** the port may be **damaged**. §11.7 drove
> ~10 V through 1 kΩ into every pin for a full session before the AWG High-Z bug was found (§11.8),
> and the read-head FPC clip broke during teardown (§11.11). "The mic reads correctly" tests the
> LCD, not the port. See `review.md` §4.

**Photo index** (`board_teardown/`): `PICT0001` exterior (TwinForCe/USB Mic); `PICT0011` full
battery-side board; `PICT0022/0023/0028/0037` connector + jumper matrix + Q1/Q2 close-ups.

### 11.17 Closed-case diode test — no shorts, but the intended comparison did not run (2026-07-26)

First test of the post-over-drive damage question (`review.md` §4), done entirely through the
Micro-USB breakout with the **case closed and the battery out** — no board access, no risk to the
FPC repair. OWON XDM1041 in diode mode via `dmm_lib.py`; full transcript in
`findings/diode_test_latest.txt`.

| Probe RED → BLACK | Reading |
|---|---|
| pin 4 → pin 5 | **0.0003 V** (known short — leads and breakout verified good) |
| pin 4 (GND) → pin 1 | **OL (open)** |
| pin 4 (GND) → pin 2 | **OL (open)** |
| pin 4 (GND) → pin 3 | **OL (open)** |
| pin 1 → pin 4 (GND) | **OL (open)** |
| pin 2 → pin 4 (GND) | **OL (open)** |
| pin 3 → pin 4 (GND) | **OL (open)** |

**What this establishes:** **no short and no low-resistance path from any signal pin to ground, in
either direction.** At the meter's diode-mode compliance (~1 mA / ~3 V open circuit) an OL means
roughly **> 3 kΩ**. That rules out the *most common* over-voltage failure mode — an ESD clamp that
fuses into a short — on all three signal pins. It is a real, if partial, negative for damage.

**What it does NOT establish — and the script initially claimed otherwise.** The run printed
*"MATCHED → no asymmetry between the symmetric inputs; no evidence of over-drive damage."* **That
verdict was a bug and is retracted.** An overload returns a ~1e9 sentinel rather than a voltage, so
comparing pin 2 against pin 3 computed `1e9 − 1e9 = 0.0` and declared a perfect match. Both pins
were simply *open*; the comparison never ran. The same bug produced the note that pin 1 "reads like
the inputs," which was likewise sentinel-vs-sentinel.

With no working-clamp reading anywhere, there is **no baseline to compare against**, so this test
cannot distinguish healthy protection structures from destroyed ones. The damage question is
**partially addressed, not settled**. (`diode_test.py` now guards every comparison against the
sentinel and says so explicitly when everything reads open.)

**On pin 1 specifically:** open in *both* directions is exactly what an open-collector NPN with a
floating base does — battery out means the 330 kΩ base resistor pulls to an unpowered node, so the
transistor is off in both polarities. That is mildly **consistent with** the inferred topology
(`review.md` §5.1a), not against it.

**One observation worth keeping:** pins 2/3 reading fully open to ground is a *little* surprising
for directly-connected CMOS inputs, which usually show a substrate diode from GND to the pin. It
may mean something sits in series (a resistor, or the `J10–J81` matrix routing), or simply that an
unpowered die presents no return path. Not a conclusion — but it is weak evidence against "pins 2/3
land straight on MCU inputs," which is one of the §5.1a inferences.

**Follow-up that would tighten this** (still closed-case): re-run in **resistance mode** —
`python diode_test.py --mode resistance` — which measures into the MΩ range instead of stopping at
the diode-test compliance voltage, and can therefore see a partial or leaky path that reads OL
here. That would also give the pin-2-vs-pin-3 comparison an actual number to work with.

#### 11.17b Resistance-mode pass — the comparison ran, and it passes (2026-07-26)

Re-run in resistance mode, expanded to 19 placements: both ground references (not just pin 4),
and — for the first time ever — **the signal pins against each other**.

| Placement | via pin 4 | via pin 5 |
|---|---|---|
| GND → pin 1 | **OL** | **OL** |
| GND → pin 2 | **30.140 MΩ** | **30.136 MΩ** |
| GND → pin 3 | **29.999 MΩ** | **30.015 MΩ** |
| pin 1/2/3 → GND (reverse) | OL | OL |
| pin 4 ↔ pin 5 | 0.3818 Ω | — |
| pin 1↔2, pin 1↔3, **pin 2↔3** | **OL both directions** | |

**1. The three signal pins are genuinely separate nets.** Every pin-to-pin pair reads open in
both directions. So §11.15's "pins 2 and 3 are symmetric inputs, driving either works" is *not*
an artefact of them being one net, and **the three-signal-pin count that the Digimatic argument
rests on (`review.md` §10.3) survives.** This needed checking and had never been checked.

**2. Pins 2 and 3 match to 0.47 %.** 30.140 vs 29.999 MΩ — and each agrees with itself across the
two ground references to within 0.05 %. This is the symmetry baseline the diode pass could not
produce. Two independent pins tracking each other that closely is **not** what a damaged input
looks like. The damage question is now substantively answered, not merely "no shorts."

**3. Pin 1 is electrically distinct from pins 2/3 — measured, not inferred.** It reads OL in every
direction against both grounds while the inputs conduct ~30 MΩ. Same leads, same meter, same range,
same session, so **pin 1 acts as the internal control**: the 30 MΩ is a real property of pins 2/3,
not instrument leakage or flux residue. This is the first *independent electrical* support for
§5.1a's inferred topology (pin 1 on a transistor collector; pins 2/3 on input-like structures).
It does not confirm the specific MMBT3904 arrangement — only that pin 1 is a different kind of node.

**4. Pins 4 and 5 are interchangeable — verified, not assumed.** The two references agree to
<0.1 % on every measurement that produced a number. Prior sections took this from §11.3's
continuity check; it is now cross-checked at measurement level.

**Why diode mode saw nothing:** a ~30 MΩ path needs ~30 kV to pass the meter's ~1 mA diode-test
current, so it correctly reads OL there. The directionality (conducts GND→pin, not pin→GND) says
the path is a junction rather than a plain resistor — consistent with a standard lower ESD clamp
seen well below its forward voltage, i.e. leakage only.

**Status of the damage hypothesis: closed to a low residual.** No shorts, no asymmetry between the
symmetric inputs, pin 1 distinct as predicted. Combined with `review.md` §4's analysis (~6 mA
injected, topology shielding, all three pins still functional), the >9.5 V over-drive should no
longer be carried as a live explanation for anything.

### 11.18 The DATA button ALONE triggers the strobe — §11.15 corrected (2026-07-26)

Found by a **negative control** on the input-threshold sweep, then confirmed by direct capture.

**How it surfaced.** The threshold sweep (`threshold_sweep.py`, estimating the internal rail by
ramping the drive amplitude down until pin 1 stops responding) responded at *every* amplitude, all
17 steps down to a 0.42 V pin high. Taken at face value that implied a rail below ~0.9 V. Then the
negative control — **AWG output switched off entirely, button only** — also fired. **The sweep was
therefore void**, and the control was the real result.

**Confirmed by capture** (`button_only_capture.py`, 3/3 events, nothing driven, all three pins
pulled up and watched simultaneously; `findings/button_only_2026-07-26_164614.txt`):

| | event 1 | event 2 | event 3 |
|---|---|---|---|
| pin 1 longest low | **499 samp / 24.95 ms** | **499 / 24.95 ms** | **499 / 24.95 ms** |
| pin 2 samples low | **0** | **0** | **0** |
| pin 3 samples low | **0** | **0** | **0** |

Quiet check before arming confirmed the AWG was off (all pins VPP ≤ 0.25 V).

#### Three findings

**1. The button alone is the whole trigger.** A sustained 25 ms low, reproducible 3/3 — not the
mechanical/EMI press glitch §11.8 saw (that was 1–2 isolated samples; these are 499 consecutive).
**§11.15's "(DATA button held) AND (edges on pin 2 or pin 3) — both are required" is WRONG** and
is retracted. Its button-alone leg came from §11.12 Test 1, whose detection was the VMIN polling
loop covering ~4–12 % of wall-clock time. **This is the THIRD false negative traced to that loop**
(after §11.12's "mic never drives any pin" and the §11.14 mis-attribution), exactly as
`review.md` §1.3 predicted. The clock in §11.15 was incidental, not causal.

**2. Neither input is ever driven — the cleanest version of this test yet.** With no clock at all,
**both** pins 2 and 3 were unmasked *simultaneously* for the first time; every previous check had a
clock on one of them, masking it, and §11.16 only ever captured 2 of the 4 cells. Zero samples
below 1.0 V on either input across all three events. **On a button press the mic drives pin 1 and
nothing else** — no CK+DATA pair, so nothing Digimatic-shaped happens from the button on its own.
(This does not refute Digimatic, which requires REQ to be asserted; it only shows the button by
itself does not produce a frame.)

**3. The "−0.7 V open-collector low" never existed.** Measured directly from the captures, the
strobe's low region has a **median of −0.027 V and a mean of −0.03 V**, with only **4–5 of 495
samples** below −0.3 V — isolated spikes. §11.14's "driven LOW — hard, to ~−0.7 V" was VMIN
peak-detecting those spikes. The strobe low is **ground**, as a saturated NPN should give.
`review.md` §2.2 argued exactly this and is now confirmed with clean data; the sub-ground anomaly
is closed, and note it persisted with the AWG disconnected, so it was never clock-related either.

#### Still open — and now the obvious next move

The low run is again **499 of 1000 samples, starting at the trigger and running to the end of the
record**. So 24.95 ms remains a **floor, not a measurement** — `review.md` §1.2's point stands and
**the end of the pin-1 event has still never been observed.**

That matters more than it used to. The simplest reading of all this is that **pin 1 is a
"data-ready" / "request-to-send" line**: press DATA, the mic asserts a long window, and waits for
the host to clock it. Every clocking attempt in this project has driven a free-running clock
*asynchronous* to that window. So:

1. **Capture the strobe's end** — trigger on pin 1 falling with the trigger at the far LEFT of the
   record, window long enough to catch the rising edge. Gives the true window length.
2. **Then clock a burst INSIDE that window**, gated from pin 1's falling edge, at the documented
   20 % duty / 9 kHz (`review.md` §5.5a, §5.7). This is the highest-value untested experiment in
   the project and both steps are closed-case on the existing rig.

### 11.19 pin 1 is the DATA BUTTON — the mic has never driven anything (2026-07-26)

**Method: the simplest possible.** Battery **OUT**, DMM in continuity mode, leads on pin 1 and
pin 4. Press the DATA button. **The continuity buzzer sounds for exactly as long as the button is
held** — verified over a 16-second hold.

**Independently confirmed with numbers** (`findings/button_switch_2026-07-26_172315.txt`, a
`button_switch_test.py` run recovered during a 2026-08-09 audit — see the note below):

| condition, battery OUT | median | sustained |
|---|---|---|
| **control**: pin 1 jumpered to pin 4 | **0.8 Ω** | 100 %, 41 consecutive |
| button **released** | **OL (open)** | 0 % |
| button **held** | **0.8 Ω** | 55 %, 23 consecutive |

Held reads *identically to a deliberate short*, against a validated positive control, with the
mic unpowered. This is much stronger than the buzzer alone.

> **⚠ That run printed the OPPOSITE verdict, and it was nearly recorded as fact.** The script
> gated on `frac_closed >= 0.7`; the held reading was 55 %, so it declared **"NOT a switch — pin 1
> IS an MCU-driven output"**. The 55 % is nothing but reaction time — about 3.5 s of an 8 s window
> elapsed before the button went down — whereas the median and the 23-sample consecutive run are
> the physical signals, and both say *closed*. The log was never read at the time; the correct
> conclusion survived only because the buzzer was reported instead of the script output. Gate
> fixed (median + sustained run; the fraction is now printed but explicitly labelled as reaction
> time, not evidence).

**A mechanical switch conducts unpowered. A transistor cannot.** Pin 1 is therefore the DATA
button's contact, wired straight to the connector for the host cable to sense. It is not an
output, and it never was.

#### What this overturns

| Claim | Status |
|---|---|
| §11.14 "BREAKTHROUGH — the mic finally drives a connector pin" | **No device response ever occurred.** A button closed a switch |
| §11.15 "pin 1 = the mic's sole OUTPUT" | **Wrong in kind.** Pin 1 is a switch to ground |
| §11.15 "trigger = button AND edges on pin 2/3" | Already retracted in §11.18; the clock was always irrelevant |
| §11.16 "pin 1 carries no measurement information" | Right conclusion, wrong reason — it is a button |
| §11.18 ~155 ms tap / >3.2 s hold, low at ~0 V | Measurements stand; they describe **contact closure** |

**The mic has never been observed to drive any connector pin.** Every apparent device response
since 2026-07-26 was a pushbutton.

#### What it explains, all at once

The ~0 V low (a closed contact, not V<sub>CE(sat)</sub>); tracking the button exactly; the
reading-independence of §11.16; why nothing ever shifts out of pin 1; and why driving pin 1 did
nothing in §11.15 — you were fighting a closed switch.

It also **vindicates the `review.md` §10.5 lead** precisely. That noted, from the reference
Digimatic host design, that *"a second 10 kΩ biases the cable's 'data' pushbutton"* — i.e. the
button is part of the port interface rather than a private input to the tool. It is, on this unit.

#### The corrected model, and why it is encouraging

```
   pin 1  = DATA button contact   (mic -> host: "the user wants a reading now")
   pin 2  = ?  |  the actual 2-wire data interface, still undecoded
   pin 3  = ?  |  most likely CLK + DATA
   pin 4/5 = GND
```

**Two signal wires plus a button is exactly the shape of the iGaging 21-bit protocol** — host
drives CLK, mic returns DATA, and the button tells the cable's MCU when to perform a read. That is
the original §3 hypothesis, and it now has a clean pin budget. (It also argues *against* Digimatic,
which needs REQ + CK + DATA = three signals; only two remain.)

#### Why the earlier clocking attempts prove less than they appeared to

Every "clock pin 2, watch pin 3" result is weaker than recorded:

- §11.12 Test 2 used the **VMIN polling loop** (~4–12 % wall-clock coverage) — the defect behind
  three separate false negatives already (`review.md` §1.3).
- §11.16's armed captures triggered on **pin 1** — i.e. on the button — not on the data pin, and
  only ever sampled a fixed window around the press.

**No test has ever armed a trigger on a data pin during a clocked read.** That is the gap.

#### Next: the experiment is now fully automatable

Because pin 1 is a switch to ground, a **button press can be synthesised electrically** — just pull
pin 1 low. No human in the loop, so the run can be long, repeated, and unattended:

```
   AWG CH1 -> 1k -> pin 1     hold LOW = "button held"
   AWG CH2 -> 1k -> pin 2     the clock
   scope   -> pin 3           armed trigger on a FALLING edge = the mic driving DATA
```

Then sweep clock rate, duty (the documented **20 %** has never been delivered — `review.md`
§5.5a), burst framing, and the pin 2/pin 3 role swap, watching for pin 3 to be pulled low. This is
the first properly-instrumented search of the actual interface — implemented as
**`interface_sweep.py`**, with a positive control on the detection path and a clock-present guard
per combination.

#### And an inference that raises the odds: Q1/Q2 must drive pins 2 and 3

The board has **two** open-collector drivers (Q1/Q2, §11.11). Pin 1 is now known to be a passive
switch, so neither of them drives it. **That leaves pins 2 and 3 as the only candidates** — a clean
one-to-one mapping which also dissolves the long-standing "two drivers but only one output pin"
contradiction (`review.md` §2.1).

If it holds, **pins 2 and 3 are outputs as well as inputs**: the mic can pull either low. That is
precisely what the sweep is looking for, and it means the **role swap matters** — watch pin 2 while
clocking pin 3, not only the reverse. Still an inference; ringing Q1/Q2's collectors would confirm
it, and that is now the main reason to open the case.

### 11.20 Interface sweep, clock pin 2 / watch pin 3 — negative, and this one is trustworthy (2026-08-09)

First search of the real interface with a trigger armed on a **data** pin — the gap §11.19
identified. `interface_sweep.py`, unattended, button synthesised by driving pin 1 low.

**Setup.** Pull-ups 10 kΩ on pins 1/2/3; AWG CH1 → 1 k → pin 1 (LOW = button held); CH2 → 1 k →
pin 2 (clock); scope armed on **pin 3**, falling through 1.5 V, for the whole 8 s dwell.
Pre-flight passed beforehand (rail 3.010 V, all pull-ups present, each channel driving only its
own pin, divider as predicted).

**Coverage: 32 combinations** — button held/released × 9 k/2 k/500/100 Hz × 50 %/20 % duty ×
continuous/burst. The positive control (pulse pin 1 low, confirm an armed trigger fires) fired on
both runs, so the detection path was proven before any negative was recorded, and every
combination verified the clock was really present on pin 2 before arming.

**Result: pin 3 was never pulled low.** One spurious trigger (held / continuous / 500 Hz / 50 %)
was correctly classified as a glitch — captured min +2.73 V, longest-low 0 samples, i.e. it never
actually crossed the threshold. The glitch discriminator did its job.

#### A script bug that made the first pass overstate its coverage

The first run used a **fixed 10 ms burst period** while burst length is `ncycles/freq`:

| freq | burst length | vs a fixed 10 ms period |
|---|---|---|
| 9000 Hz | 2.33 ms | genuine burst + 7.7 ms gap ✓ |
| 2000 Hz | **10.50 ms** | longer than the period ⇒ **effectively continuous** |
| 500 Hz | 42 ms | continuous |
| 100 Hz | 210 ms | continuous |

So only the 9 kHz rows were genuine bursts — and **three of those four were marked VOID** by the
clock-present guard, which measured VPP over a 0.22 ms window that usually landed in the idle gap.
That is precisely the §11.8 trap ("digitising ONE window can miss a burst — it lands in the idle
gap"), quoted in the script's own docstring and then walked into. Genuine burst coverage in pass
one was **1 combination out of a nominal 16**.

Fixed both: the period is now `ncycles/freq + gap` (7 ms default, so 9.33 / 17.50 / 49.00 /
217.00 ms), and the guard window spans **two whole burst periods** and takes the max of three
measurements. The burst axis was then re-run in full — 16 combinations, all with a verified clock,
all negative.

#### What this does and does not establish

**Does:** clocking **pin 2** while watching **pin 3** produces no response, across rate, duty,
framing and button state, with a continuously-armed trigger rather than the VMIN polling loop
behind three earlier false negatives. This is the first trustworthy negative for the data
interface.

**Does not** — still untested:
- **The role swap.** Only pin 3 has ever been watched. If Q1/Q2 drive pins 2 and 3 (§11.19's
  inference), pin 2 is just as likely to be the output. Needs CH2 moved to pin 3, then
  `--clk-pin 3 --data-pin 2`. **This is the immediate next step.**
- **100 kΩ pull-ups.** At 10 kΩ a weak driver could be held near the rail (`review.md` §5.7a).
- **Amplitudes below 3 V**, and coordinated two-input drive (which needs a third source, since
  CH1 is now the button).

### 11.21 Role swap — clock pin 3 / watch pin 2 — also negative; open-loop clocking is now properly exhausted (2026-08-09)

Completes the matrix §11.20 left open. AWG CH2 moved to pin 3; pre-flight re-verified the rig
(rail 3.010 V, all three pull-ups present, CH1 driving only pin 1, CH2 only pin 3, divider as
predicted). Same 32 combinations, trigger armed on **pin 2** this time.

**Result: pin 2 was never pulled low.** No VOIDs — the §11.20 burst-period fix held, so every
combination had a verified clock. Positive control fired. Not one spurious trigger.

#### Both directions are now negative, with sound instrumentation

| clocked | watched | result |
|---|---|---|
| pin 2 | pin 3 | negative, 32 combinations (§11.20) |
| pin 3 | pin 2 | negative, 32 combinations (this section) |

64 combinations total across button held/released × 9 k/2 k/500/100 Hz × 50 %/20 % duty ×
continuous/burst, every one with an armed trigger on the watched pin and a verified clock on the
driven one. **The mic does not respond to an open-loop clock on either wire.** That hypothesis —
the original §3 "feed it a clock and it shifts out 21 bits" — is now properly dead for this unit
under these conditions, and this time the negative is not an artefact of the measurement.

#### The button makes no difference at all

Across all 64 combinations, held vs released changed nothing. Combined with §11.19 (pin 1 is a
switch to ground), the simplest reading is that **the mic's MCU does not sense the button** — it is
purely a host-side signal for the cable to act on. Not proven, but the button axis can probably be
dropped from future sweeps, halving them.

#### What could still make this a false negative — two specific variables

1. **Pull-up strength — the strongest candidate.** Everything here used **10 kΩ**. Q1/Q2's 330 kΩ
   base resistors cap their sink at ≈0.7 mA, against the 0.3 mA a 10 kΩ pull-up demands: only ~2×
   margin, where the references recommend **100 kΩ** (`review.md` §5.7a). A genuinely weak driver
   could be held near the rail and read as "never driven". **A resistor swap, and the next thing
   to try.**
2. **Drive amplitude.** Always 3 V. The internal rail is still unmeasured (§11.18's method was
   invalid), and if it is 1.8 V then 3 V into its inputs is clamping and back-feeding. Lower
   amplitudes are untested.

Beyond those, coordinated two-input drive (both wires with a phase relationship) needs a third
source — freeing CH1 by using a pin1→pin4 jumper for the button would allow it.

#### Caveat on both sweeps: mic-awake state was never verified

Nothing in the rig can tell whether the mic was awake — the pins sit at the pull-up rail either
way — and §11.7 records an earlier burst run invalidated by exactly that. Auto-off is tens of
minutes and each sweep is ~7 min, so a run that starts awake finishes awake; but neither §11.20
nor §11.21 confirmed the starting state. **Future runs should note the LCD state before and
after.** This is a systematic gap in the method, not a specific doubt about these results.

### 11.22 Low-voltage sweeps (1.8 V and 2.4 V) — also negative (2026-08-09)

Free follow-up to §11.21, pure software: no rewiring, no resistor changes. Mic confirmed awake
(LCD on, thimble moved immediately beforehand).

**Why lower the rail, not just the amplitude.** Every test since §11.12 has held a **3 V pull-up
rail on the mic's input pins**. If its internal rail is 1.8 V, that forward-biases the inputs'
upper clamps *continuously* — roughly 50 µA per pin through 10 kΩ, with no clock running at all.
Lowering `--rail` removes that condition. It also gives clean logic: with `amp == rail` the
1 k/10 k divider yields `pin_high = rail` exactly and `pin_low = rail/11`.

| rail / amp | trigger thresh | combinations | result |
|---|---|---|---|
| 1.8 V | 0.9 V | 16 | **negative** |
| 2.4 V | 1.2 V | 16 | **negative** |

Pre-flight re-verified at 1.8 V first: pins idled at 1.766 / 1.786 / 1.795 V, CH2 driving pin 3
only, divider measured 1.78 / 0.14 V against a predicted 1.80 / 0.16. Positive control fired in
both sweeps; clock verified on every combination; no spurious triggers.

The button axis was dropped to `held` alone — §11.20/§11.21 showed no held-vs-released difference
across 64 combinations — halving each run to 16.

**Running total: 96 combinations, all negative**, spanning both role assignments at 3 V and three
rail voltages on the clock-pin-3 / watch-pin-2 assignment.

**Untested cell:** low voltage on the *other* role direction (clock pin 2 / watch pin 3). It needs
CH2 moved back, and given three negatives on the reverse it is low-value — but it is a gap.

**Still the strongest remaining explanation for a false negative: the 10 kΩ pull-ups.** Note the
coupling that makes this more likely at low rail voltages, not less: the base drive for Q1/Q2 comes
from the mic's own rail, so at 3 V `Ib ≈ 7 µA` and `Ic(max) ≈ 0.7 mA` against a 10 kΩ pull-up's
0.3 mA demand — comfortable — but at a 1.8 V rail `Ib ≈ 3.3 µA` and `Ic(max) ≈ 0.33 mA`, right at
the edge. **A weak driver would be masked precisely in the low-voltage runs above.** The 100 kΩ
swap is therefore not an alternative to these tests; it is the test that makes them conclusive.

### 11.23 100 kΩ pull-ups — also negative. Open-loop RE is finished (2026-08-09)

The last identified variable, and the one `review.md` §5.7a called the strongest remaining
explanation for a false negative. All three pull-ups swapped 10 kΩ → 100 kΩ. Result: **pin 2 was
never pulled low across 32 combinations.** Positive control fired; clock verified every time.

**Why this closes the question rather than adding another negative.** The concern was that Q1/Q2's
330 kΩ base resistors cap their sink current, so a weak driver could be held near the rail. At
10 kΩ the pull-up demands 300 µA against a ~330 µA capability at a 1.8 V internal rail — genuinely
marginal. **At 100 kΩ it demands 30 µA, an 11× margin even in the worst case.** Any driver capable
of pulling the line at all would now be visible, at any plausible internal rail. The hypothesis is
dead, and low-rail × 100 kΩ does not need testing separately.

#### Two rig discoveries from the swap

**Scope probes load the node.** The DHO814's 1× passive probes are ~1 MΩ to ground — invisible
against 10 kΩ (1 % shift) but not against 100 kΩ. Measured idle levels matched the divider model
to within 6 mV: pins 2/3 at 2.74 V (one probe each), **pin 1 at 2.51 V because scope CH4 sits on
the AWG output and reaches pin 1 through the 1 kΩ series resistor, so that node carries two
probes.** `preflight.py` now models this (`--pullup-k`, `--probe-mohm`) instead of expecting the
bare rail, and its divider check cross-checks VTOP/VBASe against VPP — at 100 kΩ they returned a
plausible-but-wrong 2.68/2.48 on a pin whose VPP was 3.20, so it now falls back to VMAX/VMIN.

**There is no rig-side awake detector.** `mic_state_monitor.py` sampled all three pins ~12×/s for
90 s while the mic was switched on partway through. Over 500 samples before and 450 after:

| | mic OFF | mic ON | delta |
|---|---|---|---|
| pin 1 | 2.5056 V | 2.5053 V | −0.3 mV |
| pin 2 | 2.7343 V | 2.7342 V | −0.1 mV |
| pin 3 | 2.7435 V | 2.7434 V | −0.1 mV |

Per-sample noise is 0.8–0.9 mV, so every delta is an order of magnitude below the noise floor.
Idle level is set purely by our pull-up/probe divider and is **completely independent of the mic's
power state**. The §11.21 gap stands electrically: only the LCD can confirm awake.

**But it is resolvable procedurally, and that is now the method.** Auto-off is ~27 min; a sweep is
~7 min. Wake the mic, start within ~2 min, and the run is covered with a ~20 min margin — and the
margin is large enough that even a badly wrong auto-off estimate would not threaten it. This run
was audited exactly that way after the fact, since the LCD could not be checked at the time:

    mic woken     17:41:26      sweep started 17:43:16  (+1m50s)
    sweep ended   17:48:40      auto-off due  18:08:26  (margin 19m46s)

Even if auto-off were as short as 8 min, a run finishing at +7m14s would be covered. For this to
work the log must record both ends of the window, so `interface_sweep.py` now stamps the finish
time as well as the start. (Also established: **off and
asleep are the same state** on this mic, and **auto-off is ~27 min** — sharper than §11.7's "tens
of minutes".)

*Unexplained, recorded not chased:* one voided reading during a state change showed pin 3 at
1.53 V across three consistent samples. The controlled power-on test above shows nothing
comparable, so it was most likely a handling artefact — but it has no explanation.

#### Running total: 128 combinations, all negative

| rail | pull-up | clocked → watched | combos |
|---|---|---|---|
| 3.0 V | 10 kΩ | pin 2 → pin 3 | 32 |
| 3.0 V | 10 kΩ | pin 3 → pin 2 | 32 |
| 1.8 V | 10 kΩ | pin 3 → pin 2 | 16 |
| 2.4 V | 10 kΩ | pin 3 → pin 2 | 16 |
| **3.0 V** | **100 kΩ** | **pin 3 → pin 2** | **32** |

Each with an armed trigger on the watched pin, a verified clock on the driven one, and a positive
control on the detection path.

#### Conclusion: blind open-loop reverse engineering is finished on this unit

**The mic does not respond to an open-loop clock**, on either wire, at any rate from 100 Hz to
9 kHz, at 50 % or 20 % duty, continuous or burst-framed, with the button held or released, at
three rail voltages, at both pull-up strengths. Unlike §11.12's "exhausted" and §11.16's "reached
its limit", this negative rests on instrumentation that has been validated at every step — and the
three earlier false negatives were all caught precisely because that validation was added.

**Genuinely remaining, in descending value:**
1. **The `100-700-USB-MC` cable sniff** — `review.md` §11.2/§8. Ohm the adapter out first; if it is
   passive, the complete pinout including any REQ falls out for free. Then sniff in-line and
   correlate frames against the decimal string the HID keyboard types.
2. **A logic analyzer (~$15)** first regardless — the 1000-point screen read has limited every
   capture in this project.
3. Role swap at 100 kΩ (one lead move) and coordinated two-input drive (needs a third source).
   Low expected value now; not worth delaying the purchase for.

### 11.24 Role swap at 100 kΩ — negative. The matrix is complete (2026-08-09)

AWG CH2 moved pin 3 → pin 2; the last untested cell from §11.23. Clocking **pin 2**, watching
**pin 3**, 100 kΩ pull-ups, 32 combinations. **Pin 3 was never pulled low.** Positive control
fired, clock verified throughout, no spurious triggers despite the watched pin carrying 0.80 V of
crosstalk (dipping to ~2.34 V against a 1.5 V threshold).

Awake window self-audited from the log, which now stamps both ends: woken ~18:17, run 18:18:15 →
18:23:39, auto-off due ~18:45 — roughly 21 minutes of margin.

**Final tally: 160 combinations, all negative.**

| rail | pull-up | clocked → watched | combos |
|---|---|---|---|
| 3.0 V | 10 kΩ | pin 2 → pin 3 | 32 |
| 3.0 V | 10 kΩ | pin 3 → pin 2 | 32 |
| 1.8 V | 10 kΩ | pin 3 → pin 2 | 16 |
| 2.4 V | 10 kΩ | pin 3 → pin 2 | 16 |
| 3.0 V | 100 kΩ | pin 3 → pin 2 | 32 |
| **3.0 V** | **100 kΩ** | **pin 2 → pin 3** | **32** |

Both wire assignments, at both pull-up strengths, across three rail voltages, 100 Hz–9 kHz, 50 %
and 20 % duty, continuous and burst-framed, button held and released. Every run with an armed
trigger on the watched pin, a verified clock on the driven one, and a positive control proving the
detection path before any negative was recorded.

**§11.23's conclusion stands and is now unqualified: the mic does not respond to an open-loop
clock.** Nothing in the identified parameter space remains untested.

One preflight bug was found and fixed in the course of this (see the commit): step 4 measured the
driven pin immediately after the CH2 test switched CH1 back on, catching it mid-settle and
reporting a 0.36 V swing on a pin whose VPP was 3.2 V. The VPP cross-check added earlier did not
catch it, because VPP reads low at that same instant — the guard had been working by luck of
timing on the previous run rather than by design. Step 3, which is the check that actually
verifies the rig, settles properly and was never affected.

---

## Remaining phases (carried over from the retired `BRINGUP_PLAN.md`)

These two phases were never executed and exist nowhere else. Phase A (find CLK/DATA by clock
injection) is complete — see §11.15 — so it is not reproduced here.

### Phase B — Recover framing, bit order, sign

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

### Phase C — Ground-truth capture & calibration

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
