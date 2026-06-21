# Mxmoonfree LS-20-6 20" digital calipers

Essentially a no-name brand (except the mxmoonfree2021@outlook.com contact email address and simple website at https://mxmoonfree.com/) purchased on [Amazon](https://www.amazon.com/dp/B0925RVN51) in June 2026.

It has a Mini USB port data output interface mentioned in the description and shown in the pictures, but one of the product photos says "The data output tools need to be purchased separately." Similar to the iGaging micrometer, this is a Micro USB port but it is emphatically *not* a USB-compatible protocol.

## Status: protocol fully reverse-engineered (2026-06-21)

The data port is a proprietary ~3 V synchronous serial interface on a Micro-USB jack (clock + data + V+ + GND). Pinout, signal timing, and the 24-bit frame format are fully decoded and verified against the LCD at five known readings.

- **`claude_desktop_initial_investigation.md`** — full write-up; see **§0.5 RESULTS** for the authoritative pinout + decode.
- **`caliper_decode.py`** — reference decoder (`decode_frame`), with a passing self-test.
- **`scope_lib.py` / `capture_raw.py` / `gt_capture.py` / `decode_robust.py` / `plot_capture.py`** — the SCPI capture + decode tooling used against a Rigol DHO814 over LAN.
- **`gt_*.bin`, `cap_*.bin`, `gt_log.csv`, `*.png`** — raw scope captures and rendered plots (the ground-truth evidence).

**Quick reference:** Pin1=V+ (~3 V, body) · Pin2=CLOCK · Pin3=DATA · Pin4=V+ · Pin5=GND. 24-bit frame, LSB-first, read on clock rising edge, ~274 µs/bit, new frame every 107.2 ms. Bits 0–19 = magnitude, bit 20 = sign, bit 23 = inch flag; mm = magnitude/100, inch = magnitude/2000. **No level shifter needed** — wire straight to a 3.3 V MCU (never connect Pin1/Pin4). Next step: ESP32/RP2040 front-end.

**Caveat:** the `pre-`/`pre+` preset buttons offset the **LCD only** — the data port always outputs the raw measured value and ignores the preset, so the wire value won't match the display when a preset is active. (Confirmed by a 6-position blind test: A–E exact, F = E's position with a −0.23 mm preset → identical frame to E.)
