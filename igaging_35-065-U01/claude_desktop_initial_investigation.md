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

- [ ] Measured VDD rail voltage (pin 1 ↔ pin 5, battery in).
- [ ] Continuity-verified pin assignment for CLK (SSY) and DATA.
- [ ] Whether pin 4 (ID) is connected at all.
- [ ] Actual logic-high voltage on DATA under clock (scope).
- [ ] Confirmed clock rate the mic responds to (start ~9 kHz; check tolerance).
- [ ] Per-unit ticks/mm constant from gauge-block calibration.
- [ ] Bit framing confirmed: 21 bits, LSB-first, one's-complement, sign handling.
