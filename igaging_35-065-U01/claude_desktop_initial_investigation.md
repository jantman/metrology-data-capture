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
