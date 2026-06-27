# Mxmoonfree LS-20-6 20" digital calipers

Essentially a no-name brand (except the mxmoonfree2021@outlook.com contact email address and simple website at https://mxmoonfree.com/) purchased on [Amazon](https://www.amazon.com/dp/B0925RVN51) in June 2026.

It has a Mini USB port data output interface mentioned in the description and shown in the pictures, but one of the product photos says "The data output tools need to be purchased separately." Similar to the iGaging micrometer, this is a Micro USB port but it is emphatically *not* a USB-compatible protocol.

## Status: protocol fully reverse-engineered ✅ (2026-06-21)

The "data output" port is a **proprietary ~3 V synchronous serial interface** on a Micro-USB jack (it is **not** USB). Clock + data + V+ + GND. The pinout, signal timing, and the 24-bit frame format are fully decoded and **verified against the LCD at five known readings plus an independent 6-position blind test (all correct).** The remaining work is purely the readout hardware/firmware — see *"Picking this up later"* below.

### Pinout & wiring

Micro-USB contact order (1=VBUS, 2=D−, 3=D+, 4=ID, 5=GND). **Ignore breakout silkscreen.** All voltages referenced to **Pin 5**.

| Pin | Role | Connect to MCU? |
|---|---|---|
| 1 | V+ ≈ 3.0 V (caliper body / battery **+**) | **NO** — sits at +3 V vs. our ground |
| 2 | **CLOCK** (idles high, pulses low) | Yes → GPIO (interrupt) |
| 3 | **DATA** | Yes → GPIO (input) |
| 4 | V+ (ID, tied to body) | **NO** |
| 5 | **GND** (signal reference = battery **−**) | Yes → MCU GND |

⚠️ The caliper **body is battery POSITIVE**; the signal ground is battery negative = **Pin 5**. Never connect Pin 1/Pin 4 to a logic input, and never plug this port into a USB host (it caused a Pi 5 over-current trip).

### Signal & frame format

- Logic swings the **full ~3 V** rail, **idle high** → **no level shifter needed**; wire Pin 2/3 straight to 3.3 V MCU inputs (keep them input-only / high-Z so you don't backdrive the button-shared lines).
- **24-bit frame**, **LSB first**, **~274 µs/bit**, clock idles high and pulses low; **sample DATA on the clock RISING edge**.
- New frame **every 107.2 ms** (~9.33 Hz), transmitted continuously even when idle.

| Bits (LSB-first) | Meaning |
|---|---|
| 0–19 | unsigned magnitude integer |
| 20 | sign (1 = negative) |
| 21–22 | unused (always 0) |
| 23 | unit flag (1 = inch, 0 = mm) |

**Value:** `mm = magnitude / 100` (0.01 mm res) · `inch = magnitude / 2000` (0.0005 in res), negated if bit 20.

**Caveat:** the `pre-`/`pre+` preset buttons offset the **LCD only** — the data port always outputs the **raw measured value** and ignores the preset, so the wire value won't match the display when a preset is active. (Blind test F confirmed this: same position as E + a −0.23 mm preset → byte-identical frame to E.)

### Repo files

Decoder + capture tooling (top level):

- **`caliper_decode.py`** — reference decoder (`decode_frame(bits)` / `decode_bitstring(s)`); self-test passes. Port this logic to the MCU.
- **`scope_lib.py`** — minimal SCPI client for the Rigol DHO814 (LAN, port 5555).
- **`capture_raw.py` / `gt_capture.py` / `capture_blind.py`** — scope capture scripts.

Reverse-engineering archive (`reverse-engineering/`) — investigation write-up, analysis scripts, and raw captures:

- **`claude_desktop_initial_investigation.md`** — full write-up; **§0.5** = authoritative results, **§7** = MCU front-end implementation notes.
- **`decode_robust.py`** (waveform→bits) / **`decode_caliper.py`** / **`reveal.py`** — decode/analysis; **`plot_capture.py`** — plots.
- **`cap_*.bin` + `gt_*mm/in_*.bin`** — raw ground-truth scope captures (160 ms, 160 ns/sample); **`gt_log.csv`**; **`*.png`** plots/screenshots.

### Picking this up later (MCU front-end)

Target: an **ESP32 or RP2040** reading Pin 2/3 directly, decoding frames, and streaming readings (USB-serial, or Wi-Fi/MQTT for Home Assistant). Firmware sketch:

1. **Wire** Pin 2→GPIO (clock, interrupt-capable), Pin 3→GPIO (data), Pin 5→MCU GND. No shifter, no pull-downs into the caliper.
2. **ISR on the clock RISING edge:** read DATA, shift into a 32-bit accumulator **LSB-first**.
3. **End-of-frame:** the clock idles high ~100 ms between frames; once ≥~2 ms elapses since the last edge, the accumulated 24 bits are a complete frame. (Two intra-frame anomalies — a wider first low pulse and one ~547 µs gap after bit 3 — are far shorter than the inter-frame gap, so they won't false-trigger.)
4. **Decode** per the table above (see `caliper_decode.py`), reset the accumulator, await the next frame.
5. Emit the reading (~9 Hz).

See **§7** of the investigation doc for the full timing budget and gotchas.
