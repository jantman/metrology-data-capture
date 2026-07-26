# iGaging 35-065 "Micro-USB" Data Port — Interface Reference

Working reference for reverse-engineering and building a USB/serial interface to the
**iGaging 35-065-U01 IP65 EZ Data Twin-Force digital micrometer** (and the closely related
`35-065-U02` / `U03`). Compiled from teardown reports, DRO-scale reverse-engineering work,
and vendor product pages. Treat every electrical value here as **to-be-verified on your own
unit** — iGaging has revised pinouts and signaling across product generations.

---

## 0. TL;DR

- The "Micro-USB" jack on this mic is a **physical connector only — it is NOT USB.**
- The mic speaks iGaging's **21-bit clock/data protocol** (same as their DigiMag / EZ-View /
  AccuRemote DRO scales and the Shahe clones), **not** the Mitutoyo SPC protocol used by
  iGaging's pricier Absolute Origin / SpeedMic line.
- A plain Micro-USB cable into a PC/Pi does nothing useful and can **reset the host's USB
  bus** — don't do it (see §2).
- To read it yourself: feed a clock in, shift out 21 bits, decode to raw encoder ticks, and
  scale to a measurement. Low-voltage logic (~1.5–3 V) → **level shifting required.**
- If you don't want to build anything: buy the **official cable** (§7), which acts as a USB
  HID keyboard and "types" the reading on a button press.

---

## 1. Device facts

| Item | Value |
|---|---|
| Model | iGaging 35-065-U01 (IP65 EZ Data Twin-Force, "EZ DATA MiC") |
| Range | 0–1" / 0–25 mm |
| Resolution (display) | 0.00005" / 0.001 mm |
| Accuracy (spec) | 0.00015" / 0.003 mm |
| Repeatability (spec) | 0.0005" |
| Battery | CR2032 (3 V nominal) |
| Data port | Micro-USB-B connector, **proprietary 21-bit signaling** |

> Note on precision: the 0.00005" last display digit is below the instrument's real
> repeatability — treat the bottom digit as decorative.

---

## 2. Why a plain cable fails (and is risky)

The Micro-USB pins do **not** carry USB `VBUS`/`D+`/`D-`. They carry the mic's low-voltage
supply rail and its clock/data lines. So:

- **Nothing enumerates** — there is no USB device on the other end. `lsusb` / `dmesg` show
  no change.
- **Pressing DATA can drop/reset the whole USB bus.** A passive cable wires the host's 5 V
  `VBUS` onto the mic's ~1.5–3 V `VDD`, and the host's `D+/D-` onto the mic's clock/data. When
  the mic drives those lines, the host controller sees electrically incoherent signaling and
  resets — on a Pi (shared internal hub) that drops everything at once.

**Do not plug this mic into a real USB host with a passive cable.** Bench-power and read it
deliberately instead.

---

## 3. Protocol (21-bit iGaging)

Reported behavior (verify on your unit):

- **Host-clocked.** *You* drive the clock into the mic on the **SSY/clock** line — the mic
  does not free-run. Reported clock rate ≈ **9 kHz**.
- **21 data bits, LSB-first, one's-complement.** Handle the sign accordingly.
- **Output is RAW absolute encoder ticks — NOT the displayed value.** There is no
  zero / units / ABS-INC information in the stream; the mic just reports the encoder's
  absolute count. All of that math is done downstream (the official cable does it in an
  onboard MCU, which is why that cable carries three buttons: zero, units, readout).
- **Reported scaling:** ≈ **4030 ticks/mm** (≈ 0.25 µm/tick). Example from a teardown: closed
  and zeroed read ≈ `-109125`; opening exactly 1 mm changed the count by ≈ `+4030`.
  **Calibrate this constant per-unit against gauge blocks — do not assume.**

This protocol is the same one used by iGaging/Grizzly capacitive DRO scales, so the existing
DRO reverse-engineering work applies directly (see §8).

> Distinct iGaging protocols — don't confuse them:
> 1. **21-bit** (4-wire: VDD / clock / data / GND) — DigiMag, EZ-View, AccuRemote, **this
>    micrometer**, Shahe clones.
> 2. **Mitutoyo 52-bit Digimatic SPC** — iGaging Absolute Origin, SpeedMic, OriginCal
>    calipers (trapezoidal SPC jack). **A Mitutoyo SPC cable will NOT work on this mic.**
> 3. **Absolute DRO+ 5-wire** (adds a REQ line) — incompatible with both of the above.

---

## 4. Pinout (suggested — VERIFY by continuity)

> ⚠️ **Superseded for THIS unit — see §11.** The table below was carried over from an iGaging
> *Absolute scale*; it has been **disproven on this micrometer** (pin 1 is NOT VDD; pins 4 *and*
> 5 are GND; no rail is exposed on the connector). Kept for reference/contrast only.

Micro-USB-B pin numbering: `1 = VBUS`, `2 = D-`, `3 = D+`, `4 = ID`, `5 = GND`.

The mapping below was rung out by continuity on an iGaging **Absolute** scale board, and the
pin *positions* appear consistent across the iGaging Micro-USB family (the TouchDRO adapter
ships one Micro-USB-B footprint compatible with EZ-View, DigiMag, and Absolute DRO+ alike):

| Micro-USB pin | Signal | Notes |
|---|---|---|
| 1 (VBUS pos.) | **VDD** | Mic supply rail, ~1.5–3 V. **NOT 5 V.** |
| 2 (D-) | **CLK / SSY** | Clock — you drive this *into* the mic (~9 kHz) |
| 3 (D+) | **DATA** | Serial data *out* of the mic |
| 4 (ID) | REQ | Used on the 5-wire Absolute scale; **likely unused** on this 21-bit mic |
| 5 (GND) | **GND** | |

**Caveats:**
- The `ID → REQ` mapping comes from the 5-wire Absolute scale. The 21-bit micrometer is
  4-wire (no REQ), so pin 4 is probably not connected — confirm.
- iGaging has revised pinouts across generations. **Always ring it out before trusting it.**

Internally, the PCB of 21-bit devices typically has **labeled round test points: `VDD`,
`SSY`, `DATA`**, with ground available from a square pad or the metal frame. Use these to
disambiguate clock vs. data.

---

## 5. Bench verification checklist (do these in order)

1. **Confirm VDD / GND and measure the rail (no clock needed).**
   Put a Micro-USB-B breakout on the mic, leave the battery in, and meter pin 1 ↔ pin 5.
   The pair reading battery voltage is `VDD` (pin 1) and `GND` (pin 5). **Record the exact
   voltage** — everything downstream depends on it.

2. **Confirm clock vs. data by continuity.**
   Open the case, find the labeled `VDD` / `SSY` / `DATA` test points, and ring each to its
   connector pin. This removes all guesswork about which pin is clock and which is data.

3. **Scope it under clock.**
   The mic is **silent until clocked** — you will see nothing by pressing buttons or moving
   the spindle. Only once your MCU is driving `SSY` will `DATA` produce frames. Drive ~9 kHz,
   capture `DATA`, and confirm 21-bit frames at the expected level.

> Voltage discipline: confirm the rail before connecting anything. The family signals
> anywhere from **1.5 V to 3 V**, and **not all of these devices are 3 V-tolerant** — an
> over-voltage clock can damage them. They are **not 5 V tolerant.** Drive your clock at the
> mic's *measured* VDD, never 3.3 V or 5 V directly.

---

## 6. Hardware build (DIY interface)

Target MCU: **ESP32 or ESP8266** (either has ample speed for a ~9 kHz bit-banged clock and
read).

**Bill of materials (per mic):**
- Micro-USB-B **female breakout** board.
- **Level shifter** sized to the measured VDD ↔ 3.3 V. A BSS138-based bidirectional
  board (e.g. 4-channel) covers both lines:
  - **CLK:** ESP32 3.3 V output → shift **down** to mic VDD.
  - **DATA:** mic VDD output → shift **up** to 3.3 V so the ESP32 reads it reliably
    (a ~1.5 V high will not reliably register on a 3.3 V input without shifting).
- **Pull-up resistors** to VDD on `CLK` and `DATA` (one each) for clean edges.
- Optional **0.1 µF** decoupling/edge-cleanup cap(s).

**Power:**
- Power the mic from its own CR2032, or from a bench PSU set to the **measured VDD**.
- **Never put 5 V on pin 1.**

**Wiring summary:**
```
ESP32 GPIO (clk out) --[level shift 3.3V->VDD]--> SSY (Micro-USB pin 2 / D-)
mic DATA (Micro-USB pin 3 / D+) --[level shift VDD->3.3V]--> ESP32 GPIO (data in)
VDD  (pin 1) <--- battery or bench PSU @ measured VDD
GND  (pin 5) <--- common ground (PSU + ESP32 + level shifter)
pin 4 (ID)  --- likely NC (verify)
```

---

## 7. Software / firmware

**Read loop (outline):**
1. Drive `CLK` at ~9 kHz.
2. Sample `DATA` on the appropriate clock edge; shift in **21 bits, LSB-first**.
3. Apply **one's-complement** decode and recover the signed integer (raw encoder ticks).
4. Convert ticks → mm/inch using your **calibrated** constant (start near 4030 ticks/mm).
5. Apply your own zero offset; track units yourself (the stream carries none).

**Reference implementations to port from:**
- Yuriy's Toys iGaging scale reader (logic-analyzer-derived spec + Arduino sketch).
- Rysiu M / `rysium.com` iGaging Arduino sketch (current version referenced by the teardown).

**Calibration / validation:**
- Use **gauge blocks** as the reference. Clamp known sizes, record raw tick deltas, derive
  ticks/mm, and verify linearity across the range.
- Cross-check the computed value against the **mic's own display** for sign, zero, and the
  absolute reference.

---

## 8. Official cable (no-build alternative)

If you'd rather not build anything, the factory cable contains the MCU + buttons and presents
to a computer as a **USB HID keyboard** — press the readout button and it *types* the current
reading wherever the cursor is (spreadsheet cell, inspection sheet, etc.). Plug-and-play on
Linux/Windows, no driver. Limitations: **push-only** (no polling; reading only on button
press), and the units/ABS state are whatever the cable + mic are set to.

**Compatible sources (confirm model match when ordering):**
- **ideaengineering.us** — "iGaging Absolute Micro USB Data Cable & Control Box," ~$69.95,
  explicitly lists `35-065-U01`–`U03`.
- **Amazon `B00IO0EH16`** — iGaging/AccuRemote "SPC USB Cable for 35-Series Electronic
  Micrometers"; has the three buttons (zero, units, readout).
- **Penn Tool `35-630-USB`** — "Micro USB Data Output Kit" (verify compatibility first).

**Do NOT buy** the Mitutoyo SPC cable (`iGaging 100-700-USB` / Amazon `B00INL0BA2`) — that's
for the SPC-jack Absolute/Origin tools and will not work on this micrometer.

---

## 9. Reference links

**Direct teardown of this micrometer (most relevant):**
- Alex Whittemore — *Reading an iGaging Micrometer's Digital Output*
  https://www.alexwhittemore.com/reading-an-igaging-micrometers-digital-output/

**iGaging/Grizzly 21-bit scale protocol (same protocol family):**
- Yuriy's Toys — *Reading Grizzly/iGaging DRO Scales with Arduino*
  https://www.yuriystoys.com/2012/01/reading-gtizzly-igaging-scales-with.html
- Yuriy's Toys — *Connecting iGaging Scales to TouchDRO* (VDD/SSY/DATA test points)
  https://www.yuriystoys.com/2016/12/connecting-dro-scales-to-bluetooth-adapter.html
- Yuriy's Toys — *Connecting iGaging Absolute Scales to TouchDRO* (Micro-USB pin continuity)
  https://www.yuriystoys.com/2015/12/connecting-igaging-absolute-scales-to.html
- Yuriy's Toys — *Working with iGaging Absolute DRO+ Scales* (5-wire protocol, incompatible)
  https://www.yuriystoys.com/2015/12/working-with-igaging-absolute-dro-scales.html
- Yuriy's Toys — *Updated DRO Adapter* (3 V-tolerance warning)
  https://www.yuriystoys.com/2020/01/dro-adapter-for-igaging-scales.html
- Yuriy's Toys — *DRO Interface Pin Functions for MSP430* (21-bit clock/data pin roles)
  https://www.yuriystoys.com/2014/01/dro-interface-pin-functions-for-msp430.html
- Rysiu M — iGaging Arduino sketch
  http://www.rysium.com/rysium.docs/

**Mitutoyo/SPC (the *other* iGaging line — for contrast, not this mic):**
- circuitcrush / arduinotronics — *iGaging Micrometers and Calipers* (1.5 V signaling, level
  shifter notes, 52-bit SPC for Origin/SpeedMic)
  https://circuitcrush.com/arduino/2015/09/30/igaging-micrometers-and-calipers.html
- Instructables — *Interfacing a Digital Micrometer to a Microcontroller*
  https://www.instructables.com/Interfacing-a-Digital-Micrometer-to-a-Microcontrol/
- The Hobby-Machinist — *iGaging Origin Data Spec* thread
  https://www.hobby-machinist.com/threads/igaging-origin-data-spec.38482/
- Arduino Forum — *iGaging and Mitutoyo Calipers and Micrometers as Input Devices*
  https://forum.arduino.cc/t/igaging-and-mitutoyo-calipers-and-micrometers-as-input-devices/340713

**Product pages:**
- Penn Tool — 35-065-U01 micrometer
  https://www.penntoolco.com/igaging-0-1-ip65-ez-data-twin-force-digital-micrometer-35-065-u01/
- ideaengineering.us — Micro-USB data cable & control box
  https://ideaengineering.us/
- Amazon — B00IO0EH16 (compatible cable)
  https://www.amazon.com/iGaging-AccuRemote-Cable-Electronic-Micrometers/dp/B00IO0EH16

---

## 10. Open items to confirm on your unit

> Quick checklist below. The consolidated bench log, corrected pinout, what's been tried,
> next steps, and the safety rationale live in **§11**.

- [ ] Measured VDD rail voltage. **Bench note (this unit):** pin 1 ↔ pin 5 read **0 V**
  with battery in — pin 1 is **NOT** the supply rail here (contradicts §4), and the connector
  exposes no steady rail at all. The internal logic rail is **not on the connector**; measure
  it instead **across decoupling cap C4/C5** (device ON) — that reading is the level-shift
  reference + the safe clock-drive voltage. *(pending)*
- **Teardown note (this unit):** accessible PCB side (battery/USB side) carries only passives
  (R1/R2, C4/C5), two transistors (Q1/Q2), the Micro-USB jack, battery contacts, and a config
  **solder-jumper matrix `J10/J11…J60/J61`** (some bridged, some open — selects pinout/protocol
  for this shared iGaging sensor board). The controller is an **unmarked COB epoxy blob** on
  the LCD side — no part number obtainable, so don't pull the board for chip ID. Sensor connects
  via an orange FPC ribbon to a white connector on the accessible side.
- [ ] Continuity-verified pin assignment for CLK (SSY) and DATA. **Bench note:** **pins 4 AND
  5 are both GND** (direct continuity confirmed between them and to battery negative). By
  elimination, the three signal lines (CLK, DATA, + one more) are **pins 1, 2, 3** — confirmed.
  With the device ON, pins 1/2/3 all **float** (~−0.02 V, drifting) — no internal pull-ups;
  lines float until a host pulls them up and clocks (matches §6). Which of 1/2/3 is CLK vs DATA
  still TBD (resolve via scope + clock injection). Standard Micro-USB pin roles do NOT apply.
- [x] Whether pin 4 (ID) is connected at all → **YES, it is the GND pin** (sole continuity to
  battery negative) on this unit. This is the ground reference, NOT pin 5. Differs from both
  the Absolute-scale pinout in §4 and standard Micro-USB numbering.
- [x] Battery+ (device off) has **no continuity to any connector pin** → the connector does
  **not** pass the battery rail straight through; VDD (if exposed at all) is switched/buffered
  or simply not present on the connector. Device is self-powered by its CR2032.
- [ ] Actual logic-high voltage on DATA under clock (scope). *(Can't be measured passively —
  lines float; will read it off DATA's swing once a clock is injected.)*
- [ ] Confirmed clock rate the mic responds to (start ~9 kHz; check tolerance).
- **Bench note — passive scope result (this unit):** with a Rigol DHO814 (1X probes, DC,
  500 mV/div, 1 ms/div) doing armed single-shot edge captures on pins 1/2/3/5, **NOTHING
  triggered** across rising & exhaustive provocation: pressing Data, moving the spindle,
  toggling inch/mm and ABS/INC. The lines stay floating. → **Strongly indicates the device is
  HOST-CLOCKED (clock-slave): it emits nothing until an external clock is driven in**, matching
  §3. A free-running design would have shown periodic bursts here. Next: inject a clock to make
  it talk (and thereby identify CLK vs DATA, logic level, and framing).
- [ ] Per-unit ticks/mm constant from gauge-block calibration.
- [ ] Bit framing confirmed: 21 bits, LSB-first, one's-complement, sign handling.

---

## 11. Bench log & findings — THIS unit

> Live reverse-engineering record for this specific 35-065-U01. **Where this section conflicts
> with the assumptions in §4–§5, this section wins** — those were carried over from an iGaging
> *Absolute scale* and do not match this micrometer. Log started 2026-06-21.

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

**Photo index** (`board_teardown/`): `PICT0001` exterior (TwinForCe/USB Mic); `PICT0011` full
battery-side board; `PICT0022/0023/0028/0037` connector + jumper matrix + Q1/Q2 close-ups.

### 11.12 Pull-up / open-collector tests — negative; injection EXHAUSTED (2026-07-26)

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
  input that powers the interface** (retires the "unpowered interface" hypothesis from §11.7/11.11;
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
