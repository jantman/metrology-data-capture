# LS-20 caliper → USB HID keyboard (ESP32-S3)

Firmware that turns an **ESP32-S3** into a USB keyboard: connect it to the
Mxmoonfree LS-20-6 caliper's data port, press a button, and the current reading
is **typed** into whatever field has focus on the host (spreadsheet cell, text
box, …) — **no host-side software required**. A 2-circuit DIP switch picks the
key sent after the number (Enter / Tab / nothing).

Protocol details and the reverse-engineering archive are in the
[parent README](../README.md) and `../reverse-engineering/`. The decoder here is
a direct port of [`../caliper_decode.py`](../caliper_decode.py).

## Why ESP32-S3 (not the classic ESP32)

USB HID needs **native USB-OTG**, which only the **S3 / S2** have. The classic
ESP32-WROOM and the C3 cannot present as a USB keyboard (the C3's USB is
serial/JTAG only); they could do **BLE HID** instead, but this build targets the
S3 wired-USB path.

## Bill of materials

| Qty | Part | Notes |
|---|---|---|
| 1 | ESP32-S3 DevKitC-1 (or any S3 board with the **native USB** jack broken out) | the HID keyboard enumerates on the native-USB port |
| 1 | Micro-USB **male** breakout / pigtail | taps the caliper's data port (pins 2, 3, 5) |
| 1 | Momentary push button | trigger |
| 1 | 2-circuit DIP switch | terminator select (Enter / Tab / none) |
| 2 | ~1–10 kΩ resistor (optional) | in-line on clock/data as accidental-drive insurance |
| 1 | USB-A→USB-C cable | from the native-USB jack to the host computer (also powers the board) |

> The caliper runs from its own CR2032 — **do not** power it from the ESP32.

## Wiring

All caliper voltages are referenced to **Pin 5 (battery −)**. Micro-USB contact
order is `1=VBUS 2=D− 3=D+ 4=ID 5=GND` — **ignore any breakout silkscreen** and
verify with a meter.

| Caliper pin | Signal | ESP32-S3 |
|---|---|---|
| Pin 2 (D−) | **CLOCK** (idle high, pulses low) | **GPIO4** (interrupt input) |
| Pin 3 (D+) | **DATA** | **GPIO5** (input) |
| Pin 5 (GND) | signal ground (battery −) | **GND** |
| Pin 1 (VBUS) | V+ ≈ 3 V (body = battery **+**) | **leave unconnected** |
| Pin 4 (ID) | V+ (tied to body) | **leave unconnected** |

| Control | ESP32-S3 | Wiring |
|---|---|---|
| Push button | **GPIO6** ↔ GND | internal pull-up; active-low |
| DIP switch 1 | **GPIO7** ↔ GND | closed = LOW |
| DIP switch 2 | **GPIO15** ↔ GND | closed = LOW |

> ⚠️ The caliper **body is battery POSITIVE**. Never wire Pin 1/Pin 4 to a logic
> input, and never plug this port into a USB host (it tripped a Pi 5's
> over-current protection during RE).

No level shifter / inverter / pull-downs: the logic is the full ~3 V rail (idle
high) and reads directly on the 3.3 V GPIOs. The clock/data pins are configured
high-Z (`INPUT`, no internal pull) so the firmware never back-drives the lines,
which are shared with the caliper's front-panel buttons. The optional series
resistors are extra insurance only.

GPIO choices avoid the S3 strapping pins (0, 3, 45, 46), the native-USB pins
(19/20), and the SPI-flash/PSRAM pins (26–37), so they're safe on every S3 module
variant (N8, N16R8, …).

### Terminator DIP truth table

| DIP2 (GPIO15) | DIP1 (GPIO7) | Sent after the number |
|:---:|:---:|---|
| open | open | *(nothing)* |
| open | **closed** | **Enter** (↵, next row) |
| **closed** | open | **Tab** (→, next cell) |
| closed | closed | *(nothing)* |

## Build & flash

Uses [PlatformIO](https://platformio.org/). The DevKitC-1 has **two** USB jacks:

- **"UART"** jack (CP210x/CH340) — flashing + serial debug.
- **"USB"** jack (native OTG) — where the HID keyboard appears.

```bash
cd firmware
pio run                       # build
pio run -t upload             # flash via the UART jack
pio device monitor            # 115200 baud, watch self-test + [type] logs
```

Then plug the **native-USB ("USB")** jack into the computer that should receive
the keystrokes. The UART jack can stay connected for debug, or just power.

On boot the firmware prints a **self-test** that decodes the 5 LCD-verified
ground-truth vectors — confirm `ALL PASS` before trusting a build:

```
[selftest] decoding ground-truth vectors:
  OK   000000000000000000000000 -> 0.00     (expect 0.00)
  OK   000101111100000000000000 -> 10.00    (expect 10.00)
  ...
[selftest] ALL PASS
```

### USB-mode flag (important)

`platformio.ini` sets `-DARDUINO_USB_MODE=0` to select the **TinyUSB OTG** stack,
which `USBHIDKeyboard` requires. If the board enumerates as a serial port instead
of a keyboard, that flag (vs. the default `=1` hardware CDC/JTAG) is the first
thing to check.

## Bench-test against the LCD

After flashing, re-verify on real hardware (the RE was done on a different rig):

1. Open a text editor, click into it.
2. **Zero** the caliper, press the button → expect `0.00`.
3. Set a known gauge block (e.g. 10.00 mm) → expect `10.00`.
4. Something near full travel (e.g. 100.00 mm).
5. **Negative**: zero mid-travel, close the jaws → leading `-`.
6. Toggle the caliper to **inch** → 4-decimal output (e.g. `0.9840`).
7. Flip the DIP switches and confirm Enter / Tab / none behave per the table.

> **pre-/pre+ caveat:** with a preset offset active the LCD is shifted but the
> data port still sends the *raw* value, so the typed number won't match the
> display. Clear any preset before comparing to the LCD.

## Notes / possible extensions

- HID sends **US-layout** scancodes; digits, `.` and `-` map cleanly on US
  keyboards. On an exotic host layout, remap if `.`/`-` come out wrong.
- The typed value is the most-recent **completed** frame (≤ ~110 ms old at ~9 Hz)
  — effectively live for manual measurement.
- Want a "stream every reading" mode, an inch/mm-locked output, or a units
  suffix? Those are small changes in `typeReading()` / `formatReading()`.
