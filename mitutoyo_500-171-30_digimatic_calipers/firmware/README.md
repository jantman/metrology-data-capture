# Mitutoyo Digimatic caliper → USB HID keyboard (ESP32-S3)

Firmware that turns an **ESP32-S3** into a USB keyboard: tap the CK/DATA/GND lines of a
**500-171-30** caliper's **959149** SPC cable, press the **button on the cable**, and the reading
is **typed** into whatever field has focus on the host — **no host-side software**. A 2-circuit
DIP switch picks the key sent after the number (Enter / Tab / nothing).

Pinout, front-end circuit, protocol and bring-up sequence are in the
[parent README](../README.md). The decoder here mirrors
[`../digimatic_decode.py`](../digimatic_decode.py).

> ⚠️ **Not yet run against a caliper.** The build compiles and its self-test passes, but every
> protocol constant in it is desk research until parent-README bring-up steps 3–4 are done.

## Passive listener

The firmware **never drives a wire into the caliper**. The 959149's DATA switch grounds REQ, which
is what makes the tool emit a frame; the ESP32 only watches. REQ is not wired to the MCU at all.

Consequences:

- The wedge cannot request a reading on its own — the cable's button is the only trigger. Adding
  REQ later is one FET and one GPIO.
- Readings are event-driven, not streamed. Unlike the LS-20 firmware there is no staleness check,
  because nothing arrives unless the operator just asked for it.
- **One keystroke per press:** after typing, another frame is only eligible once the clock has been
  quiet for 250 ms (`QUIET_US`), so holding the button cannot spray values. Set `STREAM_MODE 1` to
  type every frame instead.

## Why ESP32-S3 (not the classic ESP32)

USB HID needs **native USB-OTG**, which only the **S3 / S2** have. The classic ESP32-WROOM and the
C3 cannot present as a USB keyboard (the C3's USB is serial/JTAG only).

## Wiring

All voltages referenced to **Digimatic pin 1 (GND)**. Each signal reaches the GPIO through the
front end described in the parent README (100 kΩ pull-up to 3V3 + 1 kΩ series, or the comparator
fallback).

| Digimatic pin | Signal | ESP32-S3 |
|---|---|---|
| 1 | GND | **GND** |
| 2 | **DATA** | **GPIO5** |
| 3 | **CK** | **GPIO16** (interrupt) |
| 4 | RDY (optional, diagnostic) | **GPIO6** |
| 5 | REQ | **leave unconnected** |

| Control | ESP32-S3 | Wiring |
|---|---|---|
| DIP switch 1 | **GPIO7** ↔ GND | internal pull-up; closed = LOW |
| DIP switch 2 | **GPIO15** ↔ GND | internal pull-up; closed = LOW |

GPIO choices match the LS-20 build: clear of the S3 strapping pins (0, 3, 45, 46), the native-USB
pins (19/20) and the flash/PSRAM pins (26–37), so they are safe on every S3 module variant, and all
on one header side.

### Terminator DIP truth table

| DIP2 (GPIO15) | DIP1 (GPIO7) | Sent after the number |
|:---:|:---:|---|
| open | open | *(nothing)* |
| open | **closed** | **Enter** (↵, next row) |
| **closed** | open | **Tab** (→, next cell) |
| closed | closed | *(nothing)* |

## Constants to set from bench measurements

Both live at the top of `src/main.cpp`:

| Constant | Default | Set it from |
|---|---|---|
| `SAMPLE_ON_RISING` | `0` (sample on the CK **falling** edge) | `spc_capture.py` — whichever edge decodes to the LCD value |
| `FRAME_GAP_US` | `5000` | must exceed the largest intra-frame gap the capture reports, and stay well under the gap between two button presses |

Wire polarity needs no constant: the decoder infers it from the `0xFFFF` preamble on every frame.

## Build & flash

Uses [PlatformIO](https://platformio.org/) Core. The DevKitC-1 has **two** USB jacks:

- **"UART"** jack (CP210x/CH340) — **flashing + serial debug**.
- **"USB"** jack (native OTG, GPIO19/20) — where the **HID keyboard** enumerates.

### 0. Prerequisites

- PlatformIO Core on a **supported Python (3.11–3.13)** — **not** 3.14, which breaks PlatformIO's
  package metadata. On Arch, run it from a pinned venv.
- Serial access: be in the **`uucp`** group (Arch; Debian/Ubuntu use `dialout`).

### 1. Build

```bash
cd firmware
pio run
```

Expected tail (sizes in this ballpark):

```
RAM:   [=         ]  12.2% (used 40140 bytes from 327680 bytes)
Flash: [=         ]  11.5% (used 383448 bytes from 3342336 bytes)
========================= [SUCCESS] Took 7.96 seconds =========================
```

### 2. Flash (over the UART jack)

```bash
pio run -t upload                       # auto-detects the CP210x/CH340 port
# pio run -t upload --upload-port /dev/ttyUSB0   # if auto-detect picks wrong
```

If the upload stalls at "Connecting….." hold **BOOT**, tap **RESET**, release **BOOT**, re-run.

### 3. Verify the self-test (over the UART jack)

```bash
pio device monitor                      # 115200 baud
```

On boot the firmware decodes synthesized frames in both wire polarities, checks that either sign
convention reads negative, and checks that garbage is rejected — all with no caliper attached:

```
[selftest] synthesized frames, both wire polarities:
  OK   std 0.00     mm (expect 0.00)
  OK   inv 0.00     mm (expect 0.00)
  ...
  OK   sign nibble 1 and 8 both negative
  OK   garbage frame rejected
[selftest] ALL PASS
[setup] ready -- press the DATA button on the caliper cable
```

These vectors are **synthesized from the spec**, so `ALL PASS` proves the bit arithmetic is
self-consistent — not that the spec matches the instrument. That is what the bench test is for.

Each received frame is also logged here, e.g. `[type] 12.34 mm  (frame=0x…, as-wired, term=1)`,
including frames that were rejected or suppressed — the fastest way to debug a front end.

### 4. Use it as a keyboard

Plug the **native-USB ("USB")** jack into the computer that should receive the keystrokes (it
powers the board too). Click into a field and press the button on the caliper cable.

### USB-mode flag (why the `build_unflags` line exists)

`USBHIDKeyboard` needs the **TinyUSB OTG** stack (`ARDUINO_USB_MODE=0`), but the
`esp32-s3-devkitc-1` manifest forces `=1` (hardware CDC/JTAG). `platformio.ini` strips that with
`build_unflags` and sets `=0`. **If the board ever enumerates as a serial port instead of a
keyboard, check this flag first.**

## Bench-test against the LCD

1. Open a text editor, click into it.
2. **Zero** the caliper, press the cable button → expect `0.00`.
3. A known gauge block (e.g. 10.00 mm).
4. Something near full travel (e.g. 140.00 mm).
5. **Negative**: zero mid-travel, close the jaws → leading `-`.
6. Toggle the caliper to **inch** → 4-decimal output (e.g. `0.9840`), unit taken from the frame.
7. Flip the DIP switches and confirm Enter / Tab / none behave per the table.
8. Hold the button down: expect exactly **one** value typed, not a stream.

## Notes / possible extensions

- HID sends **US-layout** scancodes; digits, `.` and `-` map cleanly there. Remap if `.`/`-` come
  out wrong on an exotic host layout.
- No unit suffix is typed — just the number, so it drops straight into a spreadsheet cell. The unit
  is available in `Reading.unit` if you want it appended.
- Want REQ-driven readings (a button on the wedge, or continuous polling)? Drive REQ **open-drain
  only** — an N-FET/NPN pulling it to GND, never a push-pull 3.3 V output into a 1.55 V input.
