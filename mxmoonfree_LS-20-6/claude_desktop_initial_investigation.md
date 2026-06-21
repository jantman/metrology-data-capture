# Mxmoonfree LS-20 Digital Caliper — "Mini/Micro USB" Data Port Reverse-Engineering Guide

A working reference for confirming the pinout and building a hardware/software interface
to log measurements from the Mxmoonfree LS-20 digital caliper.

| Field | Value |
|---|---|
| Tool | Mxmoonfree 20" / 500 mm long-jaw digital caliper |
| Model / part | LS-20 / LS-20-6 |
| UPC | 735279171235 |
| Listing | https://www.amazon.com/dp/B0925RVN51 |
| Seller contact | mxmoonfree2021@outlook.com |
| Battery | CR2032 (3 V coin cell) |
| Resolution | 0.0005" / 0.01 mm |
| "Data output" connector | Micro/Mini-USB receptacle (physical only — **not** USB) |

---

## 0. TL;DR — read this first

- The "data output interface" is a **proprietary low-voltage synchronous serial port** (clock +
  data + Vdd + ground) that merely *reuses a Micro-USB connector* as a cheap physical jack. It does
  **not** speak USB.
- **Do not plug this port into any USB host again** (PC, charger, hub, or the Pi). The pin that a USB
  host drives as +5 V VBUS lands on the caliper's internal ~1.5 V serial/power circuitry. That is what
  caused the Pi 5's `over-current change` event and the bus disconnect: the Pi's USB power controller
  tripped its over-current protection to defend itself. Repeating it risks damaging the caliper's
  measurement ASIC and/or the Pi's USB power path.
- The signals are well below logic level (~1.5 V) and need a level shifter to be read by a 3.3 V
  MCU / Pi GPIO.
- You do **not** need to open the caliper. Everything is exposed on the connector pins; access them
  with a **Micro-USB *male* breakout board** used as a passive mechanical fan-out.

---

## 1. What the port actually is

Cheap digital calipers with a "data output" feature almost universally emit a proprietary synchronous
serial stream — one clock line, one data line, plus power and ground. A large number of them, including
VINCA-branded units that are the most-documented analog to this one, put that proprietary signal on a
Micro-USB connector purely for cost/availability reasons. There is no USB transceiver inside.

The widely-reported format is a **24-bit synchronous serial frame**, clocked out a couple of times per
second, at a logic level too low (~1.2–1.5 V) to read directly with a 3.3 V part — hence the need for a
level shifter. This is the same pattern across most caliper brands; only the connector and minor
protocol details vary.

References:
- Hackaday — VINCA Reader (USB + Wi-Fi interface, the closest precedent to this caliper):
  https://hackaday.com/2022/10/17/custom-interface-adds-usb-and-wi-fi-to-digital-calipers/
- Hackaday — digital caliper tag (multiple related projects):
  https://hackaday.com/tag/digital-caliper/
- Hackaday — calipers → Raspberry Pi via the serial interface:
  https://hackaday.com/2019/07/04/hacked-calipers-make-automated-measurements-a-breeze/

---

## 2. Why the Pi reported `over-current change`

On a real Micro-USB host connection, the host supplies +5 V on VBUS (pin 1) and expects D+/D-/GND on the
others. On this caliper those physical positions are wired to its own ~1.5 V serial/power lines. Plugging
into the Pi pushed 5 V into low-voltage circuitry and/or presented a near-short through the caliper
front-end. The Pi's downstream USB power controller saw excess current, tripped over-current protection,
and shut down the bus (that's the repeating `over-current change` log until unplug). Protection most
likely saved both ends — but don't rely on that twice.

---

## 3. The serial protocol (what to expect, then confirm)

There are a few protocol variants in the wild. Treat the following as the **likely** format and confirm
empirically (Section 5).

### Most common modern format ("24-bit binary")
- One 24-bit packet sent roughly every **~100–126 ms**.
- **LSB first**, clocked on the rising edge.
- Bit layout (counting from the last/MSB bit sent backward):
  - inch/mm flag bit (set = inches)
  - sign bit (set = negative)
  - remaining ~21 bits = unsigned integer = **100 × value-in-mm** (or **2000 × value-in-inch**)
- Reference: https://github.com/eadf/esp8266_bitseq/wiki/caliper

### Alternate format ("two 24-bit groups")
- Long start bit, a 23-bit group, a long middle bit, another 23-bit group, long stop bit.
- Example captured timings: start bit ~58.76 µs, each data bit ~**13.02 µs**, ~299 µs per 23-bit group.
- Data changes while clock is **high**; safest to **read on the clock's falling edge**.
- Reference (with logic-analyzer traces): https://www.robotroom.com/Caliper-Digital-Data-Port-2.html

### Other documented variants
- Six 4-bit (BCD-style) nibbles within a 24-bit stream — Yuriy's Toys:
  https://www.yuriystoys.com/2013/07/chinese-caliper-data-format.html
- 48-bit "Chinese Scales" format (Shumatech) — older indicators/scales; search "Shumatech Chinese Scales".
- General protocol + 4-pin description (1.5 V supply / clock / data / ground):
  https://sites.google.com/site/marthalprojects/home/arduino/arduino-reads-digital-caliper
  (links onward to the pcbheaven "Chinese BCD" protocol page)

> **Note:** The clock/data pins are frequently **shared with the front-panel buttons**. Pulling those
> lines low can trigger button functions, so any interface must stay **input-only / high-impedance**
> toward the caliper.

---

## 4. Tooling

On-hand and relevant:
- Digital oscilloscope — **primary discovery tool** (separate clock vs. data, capture levels/timing).
- Bench DMM — find GND and Vdd; rough pin ID.
- ESP32 — capture/decode front-end; optional Wi-Fi/MQTT push.
- Flipper Zero — logic-analyzer app → PulseView, useful for decode/verify **after** level shifting.
- Level shifters, RPi GPIO breakouts.

Need to obtain:
- **Micro-USB *male* breakout board** exposing all 5 contacts to individual pads. (Avoid sacrificed USB
  cables — they typically carry only 4 conductors and omit the ID pin, which the caliper may use.)

---

## 5. Pinout confirmation procedure

> Safety rule for every step: **never apply external power to any pad.** The caliper powers itself from
> its CR2032. The breakout is a passive fan-out only; ignore its USB silkscreen labels.

### Step 1 — Establish ground
- Open the battery door (not "opening the caliper"); confirm battery negative is bonded to the metal beam.
- Caliper **off**, DMM in continuity: find the breakout pad continuous with the frame/beam. **That pad = GND**
  and is the reference for all measurements.

### Step 2 — Find Vdd (DMM)
- Caliper **on** and idle. Black probe on GND. Measure each remaining pad (DC volts).
- The pad sitting at a steady **~1.5 V** is **Vdd** (internal regulated rail; note the cell is 3 V CR2032,
  so confirm the actual rail rather than assuming). **This number drives the level-shifter design.**
- Clock/data pads read jumpy intermediate averages on a DMM; the unused pad likely floats.

### Step 3 — Separate clock vs. data and capture parameters (scope)
- Scope ground clip on caliper GND; probe each active pad. Single-shot trigger on an edge; **slide the
  jaws** to force a transmission.
- **Clock** = uniform pulse train: a burst of ~24 evenly spaced pulses, repeating ~every 100–126 ms.
- **Data** = pattern within the burst that changes with the reading.
- Record the four parameters that determine the whole build in the table below.

### Step 4 — Identify the format
- Single 24-bit frame vs. two 24-bit groups vs. six-nibble BCD (compare against Section 3).

### Parameters to record

| Parameter | Expected (confirm!) | Measured |
|---|---|---|
| GND pad (connector position) | continuous w/ frame | |
| Vdd pad / voltage | ~1.5 V | |
| Clock pad (connector position) | — | |
| Data pad (connector position) | — | |
| Unused/ID pad | floating | |
| Logic-high voltage (Vih) | ~1.2–1.5 V | |
| Bit period (intra-burst) | ~13 µs | |
| Packet interval | ~100–126 ms | |
| Clock idle state | (high/low?) | |
| Data valid on edge | falling (read), changes on high | |
| Bit order | LSB first | |
| Format variant | 24-bit binary (likely) | |
| Scale factor | 100×mm / 2000×inch | |
| Sign bit position | — | |
| Inch/mm flag bit position | — | |

---

## 6. Hardware: level shifting

The caliper's ~1.5 V logic-high is **below** the ~1.8–2.0 V input threshold of a 3.3 V MCU / Pi GPIO, so
it won't register without shifting up.

- **Avoid** typical BSS138 bidirectional level-shifter modules here — they are **marginal at a 1.5 V low
  side** (MOSFET Vgs threshold eats too much of the swing). They can also backdrive the caliper's
  button-shared lines.
- **Preferred:** a discrete **NPN common-emitter inverter** per line (base resistor from the caliper
  signal, collector pull-up to 3.3 V). Presents high impedance to the caliper and shifts up cleanly.
  It **inverts**, so account for that in the decode (or re-invert in software/another stage).
- **Alternative:** a comparator biased around ~0.8 V on each line.

Keep both interface lines **input-only / high-Z toward the caliper** to avoid triggering its buttons.

---

## 7. Capture architecture

**Recommended: small MCU front-end, not direct Pi bit-banging.**

- Intra-burst bit timing (~13 µs/bit) is hard to capture reliably from Linux userspace.
- On the **Pi 5** specifically: GPIO is behind the new **RP1** controller, so legacy `RPi.GPIO` does not
  work — use `lgpio` / `libgpiod` if you must read on the Pi directly.
- Better: an **RP2040 (Pico) / ESP32 / Arduino** does the timing-critical capture + 24-bit decode, then
  streams clean ASCII (or JSON) readings to the Pi over USB-serial. Bonus: this **electrically isolates**
  the Pi from the caliper.
- An **ESP32** additionally enables a Wi-Fi/MQTT push (à la the VINCA Reader project) for logging into a
  home-lab / Home Assistant pipeline.

### Capture algorithm (typical)
1. Interrupt on the clock edge (per measured polarity).
2. Sample the data line on the stable edge; shift bits into an accumulator (LSB-first).
3. Detect end-of-packet via the inter-burst gap (~100+ ms idle) → finalize the 24-bit word.
4. Extract value bits, sign bit, inch/mm flag; apply scale factor (÷100 for mm, ÷2000 for inch).
5. Emit reading.

---

## 8. Decode + ground-truth verification

1. After level shifting, capture the bitstream with the **Flipper logic-analyzer app → PulseView**, or
   print raw bits from the ESP32.
2. Verify the decoded value against the **LCD** at known points:
   - zero,
   - one or two gauge blocks of known size,
   - something near full travel,
   - a negative reading (zero mid-travel, then close the jaws),
   - toggle the inch/mm button to locate that flag bit.
3. When the decoded integer tracks **100 × mm** and the sign/unit bits flip correctly, the format is
   confirmed.

---

## 9. Suggested build order (checklist)

- [ ] Acquire Micro-USB **male** breakout (all 5 pins exposed).
- [ ] Step 1–2: confirm GND and Vdd with DMM; record Vdd.
- [ ] Step 3–4: scope the lines; record bit period, packet interval, clock idle, data edge, format.
- [ ] Build per-line NPN inverter (or comparator) sized to the measured Vdd.
- [ ] Bring shifted clock/data into ESP32 (or Pico); print raw 24-bit packets.
- [ ] Implement decode (LSB-first, sign, inch/mm, scale factor).
- [ ] Ground-truth against LCD across the points in Section 8.
- [ ] (Optional) ESP32 Wi-Fi/MQTT → home-lab / Home Assistant logging.

---

## 10. Reference links

- VINCA Reader (Hackaday): https://hackaday.com/2022/10/17/custom-interface-adds-usb-and-wi-fi-to-digital-calipers/
- Digital caliper tag (Hackaday): https://hackaday.com/tag/digital-caliper/
- Calipers → Raspberry Pi (Hackaday): https://hackaday.com/2019/07/04/hacked-calipers-make-automated-measurements-a-breeze/
- 24-bit data format + traces (Robot Room): https://www.robotroom.com/Caliper-Digital-Data-Port-2.html
- Caliper pinouts (Robot Room): https://www.robotroom.com/Caliper-Digital-Data-Port.html
- 24-bit protocol writeup (eadf / GitHub): https://github.com/eadf/esp8266_bitseq/wiki/caliper
- Chinese caliper data format (Yuriy's Toys): https://www.yuriystoys.com/2013/07/chinese-caliper-data-format.html
- Arduino reads digital caliper (martin's projects): https://sites.google.com/site/marthalprojects/home/arduino/arduino-reads-digital-caliper
- Product listing: https://www.amazon.com/dp/B0925RVN51

*Some protocol/voltage figures above are typical values reported by third parties for similar calipers;
treat them as starting points and confirm against your own scope/DMM captures.*
