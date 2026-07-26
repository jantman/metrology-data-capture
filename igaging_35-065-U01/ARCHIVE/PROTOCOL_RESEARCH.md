# iGaging 35-065-U01 — Online protocol research (2026-07-17)

Two independent web-research passes, cross-checked. Persisted here so the bench work can lean
on it. **External evidence, not yet bench-confirmed on this unit** — items marked ⚠ must be
verified empirically (Phase B/C).

## Device & protocol identity (high confidence)
- **35-065-U01 = iGaging "IP65 EZ Data Twin-Force" digital micrometer**, 0–1"/0–25 mm.
- Data port = **iGaging proprietary 21-bit synchronous protocol** (the "EZ-View / DigiMag /
  AccuRemote 21-bit" family). **NOT** Mitutoyo Digimatic SPC. **No REQ line.**
- **Host-clocked / clock-slave** ("the display is the master, provides the clock"). Silent
  until the reader injects a clock — matches our passive silence (§11.4) exactly.
- The on-body **DATA button does NOT self-clock a frame.** In the factory solution a
  **control-box MCU in the cable** clocks the mic and reads it; the button just triggers the
  USB/BT keyboard-type. So the button is a red herring for wire-level bring-up.
- **Official cable: iGaging `100-700-USB-MC`** (Micro-USB "Absolute Data Cable & Control Box";
  explicitly lists 35-065-U01…U03). The SPC-jack `100-700-USB` (no `-MC`) is the *wrong*,
  incompatible one. (Supersedes the guess in investigation §8.)

## Protocol parameters
| Param | Value | Notes |
|---|---|---|
| Clock | ~**9 kHz**, host-supplied, **idle LOW** | reader drives it |
| Frame | **21 pulses ≈ 2.33 ms**, then **~7 ms gap** (~100–150 Hz update) | real reader code bursts 21 + gap, NOT truly continuous |
| Bits | **21** (20 magnitude + 1 sign), **LSB-first** | |
| Sample | DATA valid ~**4.75 µs after** the clock edge | |
| Sign | ⚠ **one's-complement / sign-extend** (alexwhittemore, Yuriy) **vs** two's-complement (TouchDRO) — sources conflict; **resolve on bench** at 0 and small ± | |
| Scale | micrometer ≈ **4030 ticks/mm** (~0.25 µm/tick); stream = raw absolute encoder ticks, not the LCD value | calibrate per-unit |
| DATA driver | ⚠ not stated; 21-bit refs use weak **pull-DOWNs (10–47 kΩ)** on DATA (implies push-pull, defined-low idle) — *contrast* the different Absolute DRO+ which needs pull-UPs | |

## Pin mapping (reference vs THIS unit)
Standard micro-USB 21-bit: **pin1(VBUS)=VDD, pin2(D−)=CLOCK in, pin3(D+)=DATA out, pin4(ID) &
pin5(GND)=GND**.
- On EZ-View **DRO scales**, pin1/VDD is a supply **input** from the reader (~3.3 V).
- On **THIS micrometer** it's self-powered (CR2032) and **no VDD is exposed** — §11.3 measured
  pin1 floating ~0 V, battery+ rings to no connector pin. So **pin1 is effectively unused here**
  and the working pair is almost certainly **CLOCK = pin 2, DATA = pin 3.**

## Why our continuous 9 kHz injection produced no data — candidate causes
Ranked by support + how cheap to test:
1. **Burst framing, not continuous.** Real readers (Yuriy, Rysium) clock **21 pulses then a
   ~7 ms gap**, repeating — we drove a *continuous* clock. The mic may frame on the gap and
   never start mid-stream. **Cheapest test: AWG burst mode, 21 cyc + gap.** (No re-wiring.)
2. **No pull-down on DATA.** 21-bit refs put a 10–47 kΩ pull-down on pin 3. We have none, so a
   high-Z/weakly-driven DATA line reads as pure crosstalk. **Add pull-down pin3→GND.**
3. **Pin-1 "reader attached" reference/enable.** Reference readers connect pin 1; ours floats.
   Possibly the output stage stays disabled without it. (Speculative; test last.)
4. Threshold — ruled out: we already ramped a clean idle-LOW clock to 3.0 V.
5. Wrong pin pairing — largely ruled out: we drove all three pins; but we never did so with a
   pull-down on the watched pin, so re-confirm pin2→pin3 with the pull-down in place.

## Highest-value next bench test (both agents converge)
**Burst-mode clock — 21 cycles @ 9 kHz, idle-LOW, ~3.0 V, ~7 ms gap — into pin 2, with a
10–22 kΩ pull-down on pin 3, mic ON, scope pin 3 for a 21-pulse-aligned burst.**

## Key sources
- alexwhittemore (reverse-engineered THIS mic): https://www.alexwhittemore.com/reading-an-igaging-micrometers-digital-output/
- Yuriy's Toys 21-bit (9 kHz, LSB, one's-comp, idle LOW, pull-downs): https://www.yuriystoys.com/2012/01/reading-gtizzly-igaging-scales-with.html
- TouchDRO 21-bit pinout / host-clocked (claims two's-comp): https://www.touchdro.com/resources/scales/capacitive/igaging-21-bit
- TouchDRO protocol-family differences: https://www.touchdro.com/resources/scales/capacitive/important-differences.html
- Rysium Arduino DRO (21 pulses @ 9 kHz, 4.75 µs sample delay): https://rysium.com/projects/196-arduino-dro
- shumatech 21-bit / AccuRemote test points VDD/SSY/DATA (HTTP 503 at time of research): https://www.shumatech.com/web/21bit_protocol
- Official cable 100-700-USB-MC: https://ideaengineering.us/store-3/pageid1904modelnumber100-700-usb-mc/
- Product ID: https://www.penntoolco.com/igaging-0-1-ip65-ez-data-twin-force-digital-micrometer-35-065-u01/
