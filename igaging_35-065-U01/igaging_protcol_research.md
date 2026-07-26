# Decoding the Data Output of the iGaging EZ Data Mic (35-065-U01)

**Research date:** 2026-07-26
**Target device:** iGaging "iP65 EZ Data Twin-Force" digital micrometer, 0–1"/0–25mm, P/N **35-065-U01**
**Output port:** Micro-USB *connector* (physical form factor only — not USB signalling)

> **Note on the title:** file name kept as requested (`igaging_protcol_research.md`), including the
> `protcol` spelling.

> ## ⚠ Read `BENCH_LOG.md` before acting on §0 or §7
>
> This document surveys what the *community* has published. It was written without reference to
> the bench work on this unit, and several of its higher-confidence claims are **already
> falsified here**:
>
> - **F4 / §0 / §4.1 pin mapping is wrong for this unit.** Measured: **pin 1 is the mic's only
>   output** (it drew 0.0 mA when fed 3 V, so it is not VDD); **pins 2 and 3 are inputs**, and
>   they are symmetric. Nothing shifts data out of pin 3.
> - **§7 steps 2, 3 and 5 are already done** (negative). **Step 4 is unperformable:** pin 4 is
>   hard-grounded on this unit, so REQ cannot live there.
> - **§10 open question 6 is answered:** the tool needs no external VDD.
>
> That last point cuts the other way too, and usefully: by **this document's own §3
> discriminator** — ID pin at 0 Ω to GND ⇒ 21-bit family — this unit is **not** Digimatic.
>
> Still fully applicable and acted upon: **F2** (not 5 V tolerant), **F5** (~100 kΩ pull-ups),
> **F8** (two's complement), **F9** (counts-per-unit candidates), **§4.2** (20 % duty, idle LOW),
> and the in-line cable-sniff method in §7.

---

## 0. Executive summary

There is **no vendor documentation** for this port. iGaging's own support has told users, verbatim,
that the data protocol is "a 3rd party item, so we r not be able to share information"
([Hobby-Machinist thread](https://www.hobby-machinist.com/threads/igaging-origin-data-spec.38482/)).
Everything below is community reverse-engineering, ranked by how well it is corroborated and how
directly it applies to *this* model.

The single most likely answer:

> The micro-USB port carries a **3 V, 4-wire, host-clocked synchronous serial link**. The host
> (your MCU) drives a **~9 kHz clock** on the connector's **D−** pin and the micrometer shifts out
> **21 bits, LSB first, two's complement**, on **D+**. The value is a **raw absolute encoder count**,
> not the displayed number — you must apply your own zero offset and counts-per-unit scale factor.

Confidence that some *specific* claim is right varies a lot across the details, so the document is
organised as **ranked findings** (§2) followed by full specs for each candidate protocol (§4–§6),
a bench procedure to disambiguate (§7), and reference code (§8).

---

## 1. What is established about the hardware (near-certain)

| Fact | Source |
|---|---|
| Range 0–1"/0–25 mm, resolution 0.00005"/0.001 mm, accuracy 0.00015"/0.003 mm, IP65, CR2032 | [Penn Tool 35-065-U01](https://www.penntoolco.com/igaging-0-1-ip65-ez-data-twin-force-digital-micrometer-35-065-u01/), [iGaging product page](https://www.igaging.com/ip65-ez-data-twinforce-mics-sets.html) |
| Output is a **Micro USB data output** port | same |
| Official accessory is **100-700-USB-MC**, "Micro DataConnect Cable Kit (Micro USB output to Micro USB cable plug in)" — a micro-USB lead into a **button control box** that presents a standard USB-A plug to the PC | [iGaging DataConnect kits](https://www.igaging.com/dataout-kits.html) |
| That box is a **USB HID keyboard emulator** — pressing "data" types the reading plus a carriage return into whatever app has focus; an optional foot switch (100-USB-FT) triggers it | [iGaging](https://www.igaging.com/dataout-kits.html), [ideaengineering](https://ideaengineering.us/store-3/pageid1904modelnumber100-700-usb-mc/) |
| The **same** 100-700-USB-MC cable serves the 35-A67-xx indicators and 35-065-U01…U03 micrometers | [ideaengineering](https://ideaengineering.us/store-3/pageid1904modelnumber100-700-usb-mc/) |
| iGaging sells a *separate* SPC-connector kit (100-700-USB) for its Mitutoyo-style flat-4-pin tools — so micro-USB and SPC are treated as **two distinct physical interfaces** in their catalogue | [iGaging](https://www.igaging.com/dataout-kits.html) |
| The 35-A67 indicator manual documents the port only as "Micro USB Data Output / Charging Port" — no protocol, no pinout | [35-A67-xx instruction PDF](https://www.igaging.com/index_html_files/35-A67-xx%20instruction.pdf) |

**Key architectural implication:** all the intelligence (unit conversion, formatting, keyboard
emulation) lives in the *control box*, not the tool. The box is the bus master. This is consistent
with the tool being a dumb slave that shifts out a raw count when clocked.

---

## 2. Findings ranked by confidence

### ★★★★★ Very high confidence

**F1. The micro-USB connector is a mechanical convenience only; there is no USB PHY, no enumeration,
no D+/D− differential signalling.**
This is universal across cheap Chinese/iGaging metrology tools. Plugging it into a real USB host does
nothing. Do **not** connect the tool directly to a PC USB port expecting enumeration; and be careful
that VBUS (5 V) from a real port could exceed the tool's 3 V rail.
Sources: [caliper2pc](https://www.caliper2pc.de/schieblehre/umbau/retrofit.html),
[TouchDRO](https://www.touchdro.com/resources/scales/capacitive/igaging-21-bit),
[alexwhittemore.com](https://www.alexwhittemore.com/reading-an-igaging-micrometers-digital-output/).

**F2. Logic levels are ~3 V (nominally 3.0–3.3 V), not 5 V. The device is not 5 V tolerant.**
Yuriy Krushelnytskiy (TouchDRO author) explicitly warns that on newer iGaging encoders,
"grounding or connecting the data pin … to a low-impedance 'sink' can let the magic smoke out,"
whereas older scales tolerated miswiring.
Source: [Yuriy's Toys — Connecting iGaging Scales](https://www.yuriystoys.com/2016/12/connecting-dro-scales-to-bluetooth-adapter.html).

**F3. Wire colours inside iGaging cables are not stable between production batches and must never be
used to infer pin function.** Verify by continuity to the connector shell/pins instead.
Source: same as F2.

---

### ★★★★☆ High confidence

**F4. Pin assignment on the micro-B connector follows iGaging's house convention:**

| Micro-USB pin | Standard USB name | iGaging function |
|---|---|---|
| 1 | VBUS (5 V) | **VDD, 3.0–3.3 V** (supply *into* the tool from the host box) |
| 2 | D− | **CLK / "SSY"** (clock, driven by the *host*) |
| 3 | D+ | **DATA** (driven by the *tool*) |
| 4 | ID | Ground (tied to GND on micro-B parts) |
| 5 | GND | Ground |

This mapping is documented by TouchDRO for *both* of iGaging's micro-B families (21-bit scales and
AbsoluteDRO+ scales), which is why confidence is high even though it hasn't been confirmed on a
35-065 specifically. Note the mapping **inverts** on some legacy *mini-B* AbsoluteDRO+ parts (5V=GND,
D−=Data, D+=Clock, ID=3.3 V) — so mini-B adapters are a trap.
Sources: [TouchDRO 21-bit](https://www.touchdro.com/resources/scales/capacitive/igaging-21-bit),
[TouchDRO AbsoluteDRO+](https://www.touchdro.com/resources/scales/capacitive/igaging-absolute-dro),
[Yuriy's Toys](https://www.yuriystoys.com/2016/12/connecting-dro-scales-to-bluetooth-adapter.html).

**F5. A pair of weak pull-ups (≈100 kΩ) from CLK and DATA to VDD is needed for reliable operation.**
The lines behave as open-drain/weakly-driven. Yuriy: "Pulling the lines to Vcc using a pair of
100 kOhm resistors did the trick."
Source: [Yuriy's Toys — Working with iGaging AbsoluteDRO+](https://www.yuriystoys.com/2015/12/working-with-igaging-absolute-dro-scales.html).

**F6. The reading is *not* the displayed value.** The one person who has published a capture from an
iGaging **micro-USB micrometer** in the 35-series reports the transmitted number is
"the number of absolute ticks of the internal rotary encoder" — with the mic closed and display
zeroed, he read **−109 125**; opening exactly 1 mm gave **−105 095** (a delta of 4 030).
Consequently *zeroing, unit selection, and preset are host-side functions* — which is exactly why the
official 100-700-USB-MC control box has its own zero / units / data buttons.
Source: [alexwhittemore.com](https://www.alexwhittemore.com/reading-an-igaging-micrometers-digital-output/).

---

### ★★★☆☆ Medium confidence — the most probable protocol

**F7. The 35-065 most likely speaks the "iGaging 21-bit" host-clocked protocol.**

Alex Whittemore's post is the only published reverse-engineering of an iGaging **micrometer with a
micro-USB port**, and he identifies it as the 21-bit protocol: *"feed a 9 kHz clock in on SSY, and
read out 21 bits in LSB-first one's compliment."* He describes a 35-series micrometer bought for ~$40
with a micro-USB plug on top. That is a strong match to the 35-065 family.

Caveats that keep this at three stars rather than four:
* He does not name the exact SKU (35-065-U01 vs. e.g. 35-054), and he never publishes a logic-analyzer
  capture — he says he abandoned the micro-USB breakout before capturing timing.
* iGaging markets the micro-USB port under the *"Absolute"* banner
  ("iGAGING **ABSOLUTE** Micro USB Data Cable & Control Box"), and its Absolute line uses the
  Digimatic-style protocol (see F10) — so there is a real chance of family confusion.
* iGaging's DataConnect page describes all its kits as working with products "that ha[ve an] SPC data
  port built in," which loosely implies Digimatic.

**Detailed spec → §4.**

**F8. Encoding is 21-bit two's complement, LSB first — not one's complement.**
Multiple community write-ups (Yuriy 2012, Alex 2016) say "one's compliment," but that appears to be
long-propagated loose wording. The canonical reference implementation sign-extends:

```c
// bits 0..19 shifted in LSB-first, then on clock 21:
if (X_INPUT_PORT & _BV(X_PIN_BIT))
    xValue |= ((long)0xfff00000);   // sign-extend bits 20..31
```

That is textbook two's-complement sign extension, and TouchDRO's current documentation states plainly:
*"the raw position as a 21-bit two's complement number with the least significant bit coming first."*
Sources: [Arduino-DRO source, src/Arduino-DRO.ino](https://github.com/stephenhouser/Arduino-DRO/blob/master/src/Arduino-DRO.ino),
[TouchDRO — Differences Between Capacitive Scales](https://www.touchdro.com/resources/scales/capacitive/important-differences.html).

**F9. Scale factor is ≈ 4030 counts/mm ≈ 102 360 counts/inch — but the exact constant is unresolved.**
Alex's single data point (4 030 counts per mm) is close to two "designed-looking" values:

| Candidate | counts/inch | counts/mm | µm/count | error vs. Alex's 4030 |
|---|---|---|---|---|
| 2560 × 40 = **102 400** /in | 102 400 | 4031.50 | 0.2480 | **+0.04 %** |
| **4000** /mm | 101 600 | 4000.00 | 0.2500 | −0.74 % |
| 4096 /mm (2¹²) | 104 038 | 4096.00 | 0.2441 | +1.64 % |

102 400 /in is arithmetically the best fit *and* is a tidy multiple of the 2560 counts/inch that
iGaging uses on its 21-bit linear scales. 4000 counts/mm is the more natural choice for a tool whose
metric display step is 0.001 mm (= exactly 4 counts). **Do not trust either — calibrate against gauge
blocks (§9).** A single 1 mm hand-set movement is worth roughly ±0.5 % at best.

---

### ★★☆☆☆ Lower confidence — plausible alternative

**F10. Alternative hypothesis: Mitutoyo Digimatic / SPC (52-bit) carried over the micro-USB pins.**

Reasons this can't be dismissed:
* iGaging's **AbsoluteDRO+** encoders "use the Mitutoyo SPC (Digimatic) protocol verbatim," and they
  ship with micro-B connectors using the *same* pin convention as F4 plus a REQ line.
* The 100-700-USB-MC is branded "**ABSOLUTE** Micro USB Data Cable."
* iGaging's own catalogue copy calls every DataConnect-compatible port an "SPC data port."
* A micro-USB connector has exactly the 5 conductors Digimatic needs: VDD, GND, DATA, CLK, REQ
  (REQ would land on the **ID** pin, which F4 lists as grounded on 21-bit parts — a decisive
  discriminator you can check with a meter).
* On the Hobby-Machinist thread, a user eventually got an iGaging Origin tool reading with unmodified
  Mitutoyo code after only *timing* adjustments: "It is the same as the mitutoyo, and now my same code
  can read either."
* Steve Spence's widely-mirrored Instructables build carries the standing update:
  *"Igaging Origin Series use a Mitutoyo cable and output the Mitutoyo 52 bit datastream. The code and
  schematics below work with SPC Digimatic Calipers, Micrometers, Dial indicators, and Scales from
  both companies."*

Reasons it is ranked below F7:
* Keyboard-emulating Digimatic boxes don't need zero/units buttons (Digimatic frames already carry
  sign, decimal-point position and units), yet the official micro-USB box has them — consistent with
  a raw-count tool.
* **Every one of the "iGaging = Digimatic" data points above concerns tools with the flat
  Mitutoyo-style SPC connector** (Origin series, AbsoluteDRO+), *not* the micro-USB port. And the two
  strongest of those citations are not independent — the Instructables author (`sspence`) and the
  Hobby-Machinist poster are the same person, Steve Spence. Treat it as one corroborated finding about
  the *SPC-connector* line, not two about micro-USB.

**Detailed spec → §5.** Note that Steve Spence's Instructables is the best available *working*
Digimatic reference implementation (schematic + Arduino code), even though its hardware is the 10-pin
SPC connector rather than micro-USB.

---

### ★☆☆☆☆ Low confidence — consider only if §7 rules out the above

**F11. "BIN 6" 24-bit self-clocked format.** A single 24-bit stream in six 4-bit nibbles: 20 bits of
binary position + flag bits for units and mode, self-clocked by the tool, one burst every ~40 ms with
~1.58 ms between nibbles. This is what the very similar micro-USB *Clockwise Tools* digital indicators
use (Tommy Liao's reverse engineering: clock and data taken off D+ and D−). Many low-cost Chinese
tools use it, so it is a live possibility for a rebadged iGaging.
Sources: [TouchDRO](https://www.touchdro.com/resources/scales/capacitive/important-differences.html),
[Hackster.io — Tommy Liao](https://www.hackster.io/news/tommy-liao-gets-low-cost-micrometers-talking-serial-with-an-arduino-compatible-adapter-build-91fb5fb7254e).

**F12. "BCD 7" 28-bit format** (seven nibbles = six decimal digits + sign/units/decimal-point).
TouchDRO notes this format "has all but disappeared." Listed only for completeness.

**F13. Sylvac 48-bit** (two 24-bit streams: raw position, then display-adjusted position).
No evidence linking it to iGaging; listed for completeness.

---

## 3. How to tell the families apart quickly

| Observation | Implies |
|---|---|
| Data line is idle/static until *you* drive a clock on D− | **21-bit** (F7) — host is master |
| Tool emits clock+data bursts on its own, continuously | BIN 6 / BCD 7 / Sylvac (F11–F13) |
| Tool emits bursts only while a 5th line is held low | **Digimatic** (F10) — that line is REQ |
| ID pin (4) measures 0 Ω to GND | 21-bit family (ID is grounded) |
| ID pin (4) floats / sits near VDD with a pull-up | Possibly REQ → Digimatic |
| 21 clock edges per frame | 21-bit |
| 52 clock edges / 13 nibbles per frame | Digimatic |
| 24 clock edges / 6 nibbles per frame | BIN 6 |

---

## 4. Spec: iGaging 21-bit protocol (primary hypothesis)

### 4.1 Electrical

| Parameter | Value | Notes |
|---|---|---|
| Supply | 3.0–3.3 V into connector pin 1 | Tool also has its own CR2032; supplying VDD is what wakes the port |
| Logic levels | 0 / ~3 V | **Not 5 V tolerant.** Use a 3.3 V MCU, or divide a 5 V clock (e.g. 2.2 kΩ / 3.3 kΩ) |
| CLK | Host → tool, on D− (pin 2) | Push-pull from host is fine |
| DATA | Tool → host, on D+ (pin 3) | Weak driver; add ~100 kΩ pull-up to VDD |
| Pull-ups | ~100 kΩ CLK→VDD and DATA→VDD | Recommended |
| Encoder PCB test points (if you open it) | `VDD`, `SSY` (=clock), `DATA`; ground = square pad / frame | Use these for continuity-checking the cable |

### 4.2 Timing (from the canonical Arduino-DRO implementation)

| Parameter | Value |
|---|---|
| Clock frequency | **9 000 Hz** (community reports "9–10 kHz") |
| Clock period | 111 µs |
| Duty cycle | **20 %** — 22 µs high, 89 µs low |
| Idle level | **LOW** |
| Bits per frame | **21** clock pulses |
| Data sampling point | ~**2 µs after the falling edge** of each clock |
| Frame repetition | Host's choice. Arduino-DRO defaults to **24 Hz**; TouchDRO documents "up to 50 Hz"; Yuriy's original note says up to ~150 Hz is achievable |
| Inter-frame gap | Whatever remains of the frame period after the 21 pulses (clock held low) |

Source: [`src/Arduino-DRO.ino`](https://github.com/stephenhouser/Arduino-DRO/blob/master/src/Arduino-DRO.ino),
constants `SCALE_CLK_PULSES 21`, `SCALE_CLK_FREQUENCY 9000`, `SCALE_CLK_DUTY 20`, and
`scaleClockFirstReadDelay = F_CPU/4000000` (= 2 µs at 16 MHz).

```
CLK   ___┌─┐________┌─┐________┌─┐__ ... ___┌─┐_______________________________
         │ │22µs    │ │        │ │          │ │        (idle low until next frame)
         └─┘        └─┘        └─┘          └─┘
         |<-- 111 µs -->|
DATA  ────X b0 ───────X b1 ────X b2 ─ ... ──X b20 (sign) ────────────────────
              ↑ sample ~2µs after falling edge
```

### 4.3 Frame format

```
bit index (order of arrival):  0   1   2  ...  19   20
meaning:                       LSB ..............MSB  sign
```
* Bits 0–19: magnitude bits of a 21-bit two's-complement integer, **LSB first**.
* Bit 20: sign bit. If set, sign-extend to your word width (`value |= 0xFFF00000` for int32).
* Result: signed **absolute** encoder count, valid range ±1 048 575.

### 4.4 Converting to a dimension

```
mm    = (raw - raw_at_zero) / COUNTS_PER_MM
inch  = (raw - raw_at_zero) / COUNTS_PER_INCH
```
with `COUNTS_PER_MM` ≈ 4030 (see F9 — calibrate!) and `raw_at_zero` captured when the anvils are
closed (or against a known standard). The tool's own zero/preset/INC state does **not** affect the
raw count; on Alex's unit a freshly-zeroed, closed micrometer still read −109 125.

---

## 5. Spec: Mitutoyo Digimatic / SPC 52-bit (alternative hypothesis)

### 5.1 Signals

| Signal | Direction | Notes |
|---|---|---|
| GND | — | |
| VDD | host → tool | 1.5 V on genuine Mitutoyo; **~3 V** on iGaging parts |
| REQ | host → tool | Open-drain input. Pull **low** to request a frame; iGaging parts stream continuously for as long as REQ is held low rather than doing a strict request/ack handshake |
| CLK | tool → host | Open-collector output; data valid on the rising edge |
| DATA | tool → host | Open-collector output |
| RDY | tool → host | Present on 6-pin SPC connectors only; won't fit on micro-USB |

Open-collector ⇒ pull-ups required (100 kΩ works; some designs use 10 kΩ).

### 5.2 Frame

52 bits = **13 nibbles**, transmitted **nibble-wise with the LSB of each nibble first**.
Bit clock ≈ 150 µs/bit (≈ 6.7 kHz) on Mitutoyo gear; refresh 2–5 Hz on Mitutoyo, up to ~250 Hz on
iGaging AbsoluteDRO+.

| Nibble (1-based) | Array index (0-based) | Content |
|---|---|---|
| 1–4 | 0–3 | Preamble, all bits set (`0xF F F F`) |
| 5 | 4 | Sign: `0` = positive, `8` = negative |
| 6–11 | 5–10 | Position, 6 digits (24 bits) |
| 12 | 11 | Decimal-point position — exponent, so divisor = 10^n |
| 13 | 12 | Units: `0` = mm, `1` = inch |

Decimal-point nibble maps to a straight power of ten (`0`→÷1, `1`→÷10, `2`→÷100, `3`→÷1000,
`4`→÷10000, `5`→÷100000). Within each nibble the **LSB arrives first**, and the receiving code samples
DATA **after the clock has gone high then low** — i.e. on the falling edge.

**Critical iGaging divergence:** on iGaging AbsoluteDRO+ scales, nibbles 6–11 are **plain binary**,
not BCD — "iGaging decided to use binary encoding rather than BCD, so some flag bits are unused
and/or can be ignored." If you assume BCD you will get nonsense above digit value 9. Test both.

### 5.3 Host interface circuit (from Steve Spence's Instructables build)

REQ is an open-collector *input* on the tool and must be pulled to ground, not driven high:
an Arduino pin drives a **PN2222A** through a 10 kΩ base resistor, so `digitalWrite(req, HIGH)`
pulls REQ low and starts the frame. CLK and DATA go to MCU pins configured `INPUT_PULLUP`. A second
10 kΩ biases the cable's "data" pushbutton. Frames are polled by asserting REQ, clocking in 13
nibbles, then releasing REQ and waiting ~100 ms.

Note this schematic is for the **10-pin Mitutoyo SPC connector**, not micro-USB — you would be
reusing the *logic*, with the REQ line relocated to the micro-USB **ID** pin.

Sources: [Instructables — Interfacing a Digital Micrometer to an Arduino & VGA Monitor](https://www.instructables.com/Interfacing-a-Digital-Micrometer-to-a-Microcontrol/),
[Yuriy's Toys](https://www.yuriystoys.com/2015/12/working-with-igaging-absolute-dro-scales.html),
[TouchDRO Digimatic pinout](https://www.touchdro.com/resources/scales/pinouts/mitutoyo-digimatic-spc.html),
[imajeenyus Digimatic readout](http://www.imajeenyus.com/electronics/20140109_digimatic_interface/index.shtml),
[Arduino Forum — iGaging & Mitutoyo as input devices](https://forum.arduino.cc/t/igaging-and-mitutoyo-calipers-and-micrometers-as-input-devices/340713).

---

## 6. Spec sketch: BIN 6 (24-bit) — fallback hypothesis

* Self-clocked by the tool; no host clock, no REQ.
* One burst roughly every **40 ms** (~25 Hz); six 4-bit nibbles with ~**1.58 ms** between nibbles;
  clock rate within a nibble varies unit-to-unit.
* 24 bits = 20 bits binary position + flag bits (sign, units mm/inch, sometimes mode).
* Dialects differ in where the flag bits sit — expect to fiddle.

---

## 7. Recommended bench procedure

**Do this before writing any decode code.** It costs an hour and eliminates all the ambiguity above.

1. **Get a breakout, not a cut cable.** Buy a micro-USB male breakout board so you keep the tool's
   port intact and can probe all five pins including ID.
2. **Meter first, power off.**
   - Continuity: pin 4 (ID) ↔ pin 5 (GND). Shorted ⇒ 21-bit family (F4). Not shorted ⇒ suspect REQ ⇒
     Digimatic (F10).
   - With the tool on and a battery installed, measure each pin to GND. You are looking for a ~3 V
     rail; identify which pin the tool itself drives.
3. **Passive capture.** Hook a logic analyzer (any cheap 8-ch 24 MHz clone; sample ≥ 1 MHz) to pins
   1–5, power the tool from its own CR2032, and move the spindle.
   - If you see bursts with no external stimulus → BIN 6 / BCD 7 / Sylvac. Count the edges per burst
     (24 → BIN 6; 28 → BCD 7; 48 → Sylvac).
   - If everything is dead quiet → it's a slave: either 21-bit or Digimatic.
4. **If dead quiet, try Digimatic first** (it's the passive test): supply 3.3 V on pin 1, GND on pin 5,
   100 kΩ pull-ups on pins 2/3/4, then pull **pin 4 low**. If the tool starts emitting clock+data on
   pins 2/3, you have Digimatic — count 52 bits / 13 nibbles.
5. **Otherwise drive the 21-bit clock:** 3.3 V, 9 kHz, 20 % duty on **pin 2 (D−)**, sample **pin 3 (D+)**
   ~2 µs after each falling edge, 21 bits. Sanity-check: the value must change monotonically and
   linearly as you turn the thimble, and must sign-extend cleanly.
6. **Never drive 5 V into any pin** and never hard-ground the DATA pin (F2).

**Sniffing the official cable is the shortcut if you own one:** put the breakout in-line between the
micrometer and the 100-700-USB-MC control box and just watch. That gives you the real clock timing,
the real frame length, and — because the box is a USB HID keyboard — you can correlate raw frames
against the exact decimal string it types. That is by far the fastest route to a bit-exact spec, and
it also directly settles the counts-per-unit constant.

---

## 8. Reference implementation (21-bit, primary hypothesis)

Bit-banged, 3.3 V MCU (ESP32 / RP2040 / 3.3 V AVR). Blocking, one frame per call.

```c
// Micro-USB pin 2 (D-) -> CLK_PIN (output, idle LOW)
// Micro-USB pin 3 (D+) -> DAT_PIN (input, ~100k pull-up to VDD)
// Micro-USB pin 1      -> 3.3 V
// Micro-USB pins 4,5   -> GND
//
// 9 kHz, 20% duty: 22 us high, 89 us low. Sample ~2 us after the falling edge.

#define CLK_PIN  4
#define DAT_PIN  5

int32_t igaging_read21(void) {
    uint32_t v = 0;

    for (int i = 0; i < 21; i++) {
        digitalWrite(CLK_PIN, HIGH);
        delayMicroseconds(22);
        digitalWrite(CLK_PIN, LOW);
        delayMicroseconds(2);               // settling before sampling

        int bit = digitalRead(DAT_PIN);

        if (i < 20) {
            // LSB first: stuff into bit 20, then shift right.
            if (bit) v |= (1UL << 20);
            v >>= 1;
        } else {
            // 21st bit is the sign; sign-extend into a full int32.
            if (bit) v |= 0xFFF00000UL;
        }

        delayMicroseconds(87);              // remainder of the 111 us period
    }
    return (int32_t)v;
}

// --- usage -------------------------------------------------------------
// CALIBRATE THESE. 4030.0 is a single-data-point community estimate.
static const double COUNTS_PER_MM = 4030.0;
static int32_t zero_count = 0;

double igaging_mm(void) {
    return (double)(igaging_read21() - zero_count) / COUNTS_PER_MM;
}
```

Notes:
* `delayMicroseconds()` is adequate at 9 kHz but jittery; the production implementation
  (Arduino-DRO) drives the clock from **Timer2 in PWM mode** with compare interrupts, which lets it
  clock four scales simultaneously. If you need four axes or tight timing, copy that approach.
* Frame rate: leave ≥ 10 ms between frames to start with (~100 Hz); back off to 24 Hz if you see
  instability.
* Average 2–4 frames before displaying; the community sketches all implement weighted averaging
  because the last count or two dither.

**Canonical sources to crib from:**
* [stephenhouser/Arduino-DRO](https://github.com/stephenhouser/Arduino-DRO) — maintained fork of
  Rysiu M's sketch; see `src/Arduino-DRO.ino`, ISRs `TIMER2_COMPA_vect` / `TIMER2_COMPB_vect`.
* [Rysiu M's Arduino DRO project](https://rysium.com/projects/196-arduino-dro) — the original.
* [Yuriy's Toys — Reading Grizzly/iGaging Scales with Arduino](https://www.yuriystoys.com/2012/01/reading-gtizzly-igaging-scales-with.html) — the 2012 post that started it all.

---

## 9. Calibration procedure (needed regardless of which protocol wins)

Because the tool ships raw counts (F6), the scale factor is yours to determine and it is the largest
remaining unknown (F9).

1. Close the anvils, let the reading settle, record `raw_closed` (average ≥ 20 frames).
2. Insert a **1.000 mm** grade-0/1 gauge block (or the 0.5" / 1.000" block from a set), record `raw_1`.
3. Repeat with as large a block as the 0–1" range allows — e.g. 25 mm / 1.000". Longer baseline,
   smaller error.
4. `COUNTS_PER_MM = (raw_big - raw_closed) / block_length_mm`.
5. Compare against the candidates in F9's table. If you land within 0.05 % of 4031.50, the underlying
   constant is 102 400 counts/inch. If you land within 0.05 % of 4000.00, it's 4000 counts/mm. That
   result is worth publishing — nobody has pinned it down.
6. Cross-check linearity at 3–4 intermediate blocks before trusting the constant.
7. Sanity ceiling: at ~4030 counts/mm the full 25 mm range is ~102 000 counts, comfortably inside the
   21-bit signed range even with the large negative origin offset Alex observed (−109 125).

---

## 10. Open questions / what nobody has published

1. **Which protocol the 35-065 specifically speaks.** No capture from this exact SKU exists publicly.
2. **The exact counts-per-unit constant.** One informal data point (≈4030/mm) only.
3. **Whether the ID pin carries REQ on this tool.** Trivially answerable with a multimeter (§7.2).
4. **Whether the port supports any host→tool commands** (zero, units, sleep). The control box's
   zero/units buttons *might* be purely host-side arithmetic, or might send something back. Watching
   the in-line capture while pressing those buttons would settle it.
5. **Power behaviour.** The 35-A67 manual calls the identical port "Data Output / **Charging** Port,"
   implying VBUS is also a charge input on some models. Understand this before you feed it 3.3 V.
6. **Whether the tool needs external VDD at all**, or runs entirely off its CR2032 with the port pins
   purely signal.

---

## 11. Sources

- [Reading an iGaging Micrometer's Digital Output — alexwhittemore.com](https://www.alexwhittemore.com/reading-an-igaging-micrometers-digital-output/) — the only published RE of a micro-USB iGaging micrometer
- [TouchDRO — iGaging EZ-View DRO and DigiMag 21-Bit Scales](https://www.touchdro.com/resources/scales/capacitive/igaging-21-bit)
- [TouchDRO — iGaging AbsoluteDRO Plus Scales](https://www.touchdro.com/resources/scales/capacitive/igaging-absolute-dro)
- [TouchDRO — Differences Between Capacitive Scales](https://www.touchdro.com/resources/scales/capacitive/important-differences.html)
- [TouchDRO — Mitutoyo Digimatic SPC pinout](https://www.touchdro.com/resources/scales/pinouts/mitutoyo-digimatic-spc.html)
- [Yuriy's Toys — Reading Grizzly/iGaging Scales with Arduino (2012)](https://www.yuriystoys.com/2012/01/reading-gtizzly-igaging-scales-with.html)
- [Yuriy's Toys — Connecting iGaging Scales to TouchDRO Controller (pinouts)](https://www.yuriystoys.com/2016/12/connecting-dro-scales-to-bluetooth-adapter.html)
- [Yuriy's Toys — Working with iGaging AbsoluteDRO+ Scales](https://www.yuriystoys.com/2015/12/working-with-igaging-absolute-dro-scales.html)
- [stephenhouser/Arduino-DRO (GitHub) — reference 21-bit implementation](https://github.com/stephenhouser/Arduino-DRO)
- [Rysiu M — Arduino DRO for iGaging scales](https://rysium.com/projects/196-arduino-dro)
- [Arduino Forum — iGaging and Mitutoyo Calipers and Micrometers as Input devices](https://forum.arduino.cc/t/igaging-and-mitutoyo-calipers-and-micrometers-as-input-devices/340713)
- [learnarduinonow.com — iGaging Micrometers and Calipers](https://learnarduinonow.com/2015/09/30/igaging-micrometers-and-calipers.html)
- [Instructables — Interfacing a Digital Micrometer to an Arduino & VGA Monitor (sspence, 2012, updated 2019)](https://www.instructables.com/Interfacing-a-Digital-Micrometer-to-a-Microcontrol/) — full Digimatic schematic + Arduino code; **SPC 10-pin connector, not micro-USB**. Source of the "iGaging Origin Series … output the Mitutoyo 52 bit datastream" claim. Same author as the Hobby-Machinist thread below (not an independent corroboration)
- [Hobby-Machinist — "Igaging Origin Data Spec"](https://www.hobby-machinist.com/threads/igaging-origin-data-spec.38482/) — includes iGaging's refusal to document the protocol
- [Hackster.io — Tommy Liao's micrometer adapter (Clockwise Tools, micro-USB D+/D−)](https://www.hackster.io/news/tommy-liao-gets-low-cost-micrometers-talking-serial-with-an-arduino-compatible-adapter-build-91fb5fb7254e)
- [imajeenyus — Mitutoyo SPC Digimatic readout](http://www.imajeenyus.com/electronics/20140109_digimatic_interface/index.shtml)
- [caliper2pc — Retrofitting a Digital Caliper](https://www.caliper2pc.de/schieblehre/umbau/retrofit.html)
- [iGaging — DataConnect Data Output Kits](https://www.igaging.com/dataout-kits.html)
- [iGaging — iP65 EZ Data Twin-Force micrometers (35-065-U0x)](https://www.igaging.com/ip65-ez-data-twinforce-mics-sets.html)
- [iGaging — 35-A67-xx instruction sheet (PDF)](https://www.igaging.com/index_html_files/35-A67-xx%20instruction.pdf)
- [Penn Tool Co. — 35-065-U01 specifications](https://www.penntoolco.com/igaging-0-1-ip65-ez-data-twin-force-digital-micrometer-35-065-u01/)
- [ideaengineering.us — 100-700-USB-MC micro USB data cable & control box](https://ideaengineering.us/store-3/pageid1904modelnumber100-700-usb-mc/)
