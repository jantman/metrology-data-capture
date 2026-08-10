# Mitutoyo 500-171-30 ABSOLUTE Digimatic caliper — keyboard wedge

A USB keyboard wedge for a **Mitutoyo 500-171-30** caliper (0–6″/150 mm, 0.0005″/0.01 mm,
SR44 cell) read through a **Mitutoyo 959149** SPC connecting cable (1 m, with DATA-out switch,
10-pin Digimatic plug). Press the button on the caliper's own cable and the reading is *typed*
into whatever field has focus on the host — no host-side software.

Same idea as [`../mxmoonfree_LS-20-6/`](../mxmoonfree_LS-20-6/), but the tool here speaks a
**documented industry protocol** (Mitutoyo Digimatic/SPC) rather than an unknown one, so this
project is an interfacing job, not a reverse-engineering job.

## Status: designed, **not yet bench-verified** ⚠️ (2026-08-09)

| Piece | State |
|---|---|
| Protocol spec | Third-party desk research (sources below). **No measurement of this unit yet.** |
| Reference decoder (`digimatic_decode.py`) | Written; self-test passes on synthesized frames |
| Firmware (`firmware/`) | Written; compiles for ESP32-S3; self-test passes (verified natively against the same vectors) |
| Front-end hardware | **Decision pending one measurement** — see *The open-drain question* |
| Anything touching the real caliper | Not started |

Nothing here has seen a caliper. The bring-up sequence in *Bring-up plan* is ordered so that the
one measurement that can invalidate the hardware design happens first.

## Design decisions

- **Passive listener.** The firmware never drives a wire into the caliper. The 959149's own DATA
  switch grounds REQ, which is what makes the tool emit a frame; the wedge only watches CK and
  DATA go past. No transistor, no REQ driver, and no way for a firmware bug to push current into
  a 1.55 V instrument. The trade-off is that the wedge cannot ask for a reading on its own — the
  trigger is always the button on the cable. (Adding REQ later is a FET and one GPIO.)
- **ESP32-S3 DevKitC-1**, native-USB HID keyboard — same board, same pin conventions and same
  firmware structure as the LS-20 wedge, so the two builds stay comparable.
- **Wire polarity is detected, not assumed.** See *Frame format*.

## Pinout

The 959149 terminates in the standard **Digimatic 10-pin plug**, which mates with a
**2×5 box receptacle**. Contact assignment (Caliper2PC's Digimatic guide, corroborated by the
CircuitPython `mitutoyo` library and MicroRidge's cable documentation):

| Digimatic pin | Signal | Direction | Wedge |
|---|---|---|---|
| 1 | **GND** | — | ESP32 GND (signal reference for everything) |
| 2 | **DATA** | tool → host | GPIO5, through the front end |
| 3 | **CK** (clock) | tool → host | GPIO16, through the front end |
| 4 | **RDY** | tool → host | GPIO6, optional — diagnostic only; may be absent on calipers |
| 5 | **REQ** | host → tool | **leave unconnected** — the cable's DATA switch owns it |
| 6–10 | not connected | — | leave unconnected |

> ⚠️ **Confirm the receptacle's physical pin numbering before soldering.** "Pin 1" of a 2×5
> receptacle and "pin 1" of the Digimatic plug need not land on the same contact — the housing can
> be mirrored or rotated relative to the map above. `port_probe.py` Phase B settles it with no
> assumptions: hold the cable's DATA button and watch which pin goes to 0 V. That pin **is** REQ
> (pin 5), and everything else follows from it.

Unlike the LS-20, there is nothing dangerous about the mechanical port here: no pin sits at a
weird potential relative to signal ground, and the connector is not a USB jack that might get
plugged into a host.

## The open-drain question

This is the one thing that decides the front-end design, and the literature does not settle it.

CK and DATA are described everywhere as **open-collector outputs** — which is why every hobby
build on the web wires them straight to a 5 V or 3.3 V MCU pin with a pull-up and works. But
Mitutoyo's logic runs off a **1.55 V SR44 cell**, and published pinouts describe the tool-side
signals as "0–1.5 V". Those two descriptions imply different hardware:

| If the line is… | Then… |
|---|---|
| a **true open collector** (high-Z when idle) | our pull-up sets the high level. Pull to 3.3 V, wire straight to the GPIO, done. |
| **driven or clamped to the tool's ~1.5 V rail** | a 3.3 V pull-up fights the tool's clamp, and an ESP32-S3 GPIO (VIH ≈ 2.48 V) reads a **permanent LOW** — not one bit ever decodes. Level translation required. |

**The measurement:** fit a 100 kΩ pull-up to 3.3 V and read the idle DC level (`port_probe.py`
Phase C). ~3.3 V ⇒ open collector. ~1.5–2.2 V ⇒ clamped. Worst case injects
(3.3 − 1.5)/100 kΩ = **18 µA** into the caliper, less than its own quiescent draw and current-
limited at the bench supply, so the test itself is harmless.

### Front end A — direct (expected case)

Per line (CK, DATA, and RDY if used):

```
Digimatic pin ──┬── 100 kΩ ── +3V3
                └── 1 kΩ ──── ESP32 GPIO   (configured INPUT, no internal pull)
```

The 1 kΩ series resistor is insurance: if a GPIO is ever mis-configured as an output it can only
push ~3 mA at the tool. 100 kΩ into ~150 pF of wiring gives a ~15 µs rise — negligible against a
~650 µs bit. If `spc_capture.py` shows soft edges, drop to 10 kΩ (0.33 mA of sink current, well
within an open collector's ability).

### Front end B — level-translated (fallback, if the line reads clamped)

Put a comparator between the tool and the MCU: **LM393** (dual, one channel each for CK and DATA),
powered from 3V3, signal on one input, a ~0.75 V divider reference on the other, open-drain output
pulled to 3V3 with 10 kΩ. The line still needs its 100 kΩ pull-up. This works regardless of how
weakly the tool drives, and it does not care which way round the comparator inputs go — the
firmware detects wire polarity from the preamble either way.

A TXS0102 with a 1.8 V A-side rail is the tidier alternative if you would rather have a translator
than a comparator; it is purpose-built for open-drain lines.

## Frame format

52 bits = **13 nibbles**, transmitted nibble-wise with the **LSB of each nibble first**. One frame
per REQ assertion (i.e. per button press) — the caliper does **not** free-run.

| Nibble (1-based) | Index | Content |
|---|---|---|
| 1–4 | 0–3 | preamble, all bits set (`0xF` each) |
| 5 | 4 | sign: `0` = positive, nonzero = negative |
| 6–11 | 5–10 | six BCD digits, most-significant first |
| 12 | 11 | decimal-point position = number of decimals |
| 13 | 12 | units: `0` = mm, `1` = inch |

`value = digits / 10^dp`, negated per the sign nibble. The frame is *self-describing* — it carries
the decimal point and the unit — so the wedge formats straight from digits + dp and never touches
a float: `000123 dp=2` → `1.23`, `009840 dp=4 in` → `0.9840`, matching the LCD digit-for-digit.

Two conventions are reported **inconsistently** across sources, so both the Python decoder and the
firmware handle them defensively instead of picking one:

- **Wire polarity.** Open-collector signalling means a logic 1 may appear as a high *or* a low
  depending on the front end. Since the preamble is a constant `0xFFFF`, both decoders try each
  polarity and keep whichever produces it. A side effect: a misaligned 52-bit window has no valid
  preamble and is rejected rather than typed.
- **Sign nibble.** Sources say `0`/`8` or `0`/`1` — the same disagreement seen through a different
  within-nibble bit order. Any nonzero sign nibble is treated as negative.

Published timing (to be replaced with measurements): ~52 clocks in ~34 ms, i.e. roughly 650 µs per
bit. Firmware uses edge counting plus a gap-based resync rather than fixed delays, so a different
bit rate does not break it.

## Bill of materials

| Qty | Part | Notes |
|---|---|---|
| 1 | Mitutoyo 959149 SPC cable | tool end; already owned |
| 1 | ESP32-S3 DevKitC-1 (native USB broken out) | HID enumerates on the native-USB jack |
| 1 | 2×5 box receptacle | mates with the Digimatic plug; already owned |
| 3 | 100 kΩ resistor | pull-ups on CK / DATA / RDY |
| 3 | 1 kΩ resistor | series protection into the GPIOs |
| 1 | 2-circuit DIP switch | terminator select (Enter / Tab / none) |
| 1 | USB-A→USB-C cable | native-USB jack to the host; also powers the board |
| — | *fallback only:* LM393 + 2× 10 kΩ + divider pair | front end B |

The caliper runs from its own SR44 — **do not** power it from the ESP32, and do not connect
anything to REQ.

## Wiring

| Digimatic pin | Signal | ESP32-S3 | Front end |
|---|---|---|---|
| 1 | GND | GND | direct |
| 2 | DATA | **GPIO5** | 100 kΩ to 3V3, 1 kΩ series |
| 3 | CK | **GPIO16** (interrupt) | 100 kΩ to 3V3, 1 kΩ series |
| 4 | RDY | **GPIO6** (optional) | 100 kΩ to 3V3, 1 kΩ series |
| 5 | REQ | — | **unconnected, deliberately** |

| Control | ESP32-S3 | Wiring |
|---|---|---|
| DIP switch 1 | **GPIO7** ↔ GND | internal pull-up; closed = LOW |
| DIP switch 2 | **GPIO15** ↔ GND | internal pull-up; closed = LOW |

Terminator truth table, and build/flash steps: [`firmware/README.md`](firmware/README.md).

## Bring-up plan

Ordered so the cheapest test that can invalidate the design runs first.

1. **Map the receptacle** — `python3 port_probe.py` Phase A/B. Idle levels on every pin, then the
   DATA-button test that identifies REQ unambiguously. Fix the pin map here if it disagrees.
2. **Open-drain verdict** — Phase C of the same script. Chooses front end A or B. *Stop and
   re-read* if the answer is "clamped": front end A cannot work and building it wastes the trip.
3. **Build the front end**, then `python3 spc_capture.py "0.00mm"` — one frame on the scope.
   Confirms 52 edges, measures the bit period and intra-frame gaps, and identifies which clock
   edge carries valid data and which wire polarity is in play.
4. **Ground truth** — repeat step 3 at several known LCD readings: zero, a gauge block (e.g.
   10.00 mm), something near full travel, a negative (zero mid-travel then close the jaws), and
   one in **inch** mode. Every capture must decode to the value on the LCD. Rows accumulate in
   `gt_log.csv`.
5. **Firmware** — set `SAMPLE_ON_RISING` and `FRAME_GAP_US` from step 3's measurements, flash,
   confirm `[selftest] ALL PASS` over the UART jack.
6. **Bench-test against the LCD** — repeat the step-4 readings through the keyboard, then check
   the DIP terminator table. Also worth confirming: does the SPC output follow a **Zero/ABS**
   origin set mid-travel, or does it report the absolute scale position? (The LS-20 surprised us
   here — its preset offsets the LCD only.) Record the answer in this README.

## Repo files

- **`digimatic_decode.py`** — reference decoder (`decode_frame` / `decode_bitstring` /
  `encode_frame`); the firmware mirrors it. `python3 digimatic_decode.py` runs the self-test.
- **`port_probe.py`** — steps 1–2: guided DMM/PSU probe; pin identification and the open-drain
  determination. Logs to `findings/`.
- **`spc_capture.py`** — steps 3–4: scope capture of one frame, bit-rate/edge/polarity analysis,
  decode against a known LCD reading. Logs to `findings/` and `gt_log.csv`.
- **`selftest_analyze.py`** — offline test of `spc_capture.analyze()` against synthesized
  waveforms (both polarities, multiple presses, an intra-frame gap), so the capture pipeline is
  known-good before it is used live.
- **`scope_lib.py` / `dmm_lib.py` / `psu_lib.py`** — LAN clients for the Rigol DHO814 scope, OWON
  XDM1041 DMM and B&K 169x supply (copied from the sibling projects; networking needs Bash
  `dangerouslyDisableSandbox`).
- **`firmware/`** — ESP32-S3 → USB HID keyboard. See [`firmware/README.md`](firmware/README.md).

## Sources

Protocol and pinout are desk research until step 4 says otherwise:

- [Caliper2PC — *Connecting Mitutoyo Digimatic Devices*](https://www.caliper2pc.de/download/mitutoyo.php) — 10-pin pinout (1 = GND, 2 = DATA, 3 = CK, 4 = RDY, 5 = REQ)
- [TouchDRO — Mitutoyo Digimatic/SPC pinout](https://www.touchdro.com/resources/scales/pinouts/mitutoyo-digimatic-spc.html) — signal levels quoted as 0–1.5 V; notes level conversion is usually needed
- [imajeenyus — Mitutoyo SPC Digimatic readout](http://www.imajeenyus.com/electronics/20140109_digimatic_interface/index.shtml) — open-collector signalling, REQ pulled low to request, 13 data nibbles
- [CircuitPython `mitutoyo` library](https://circuitpython-mitutoyo.readthedocs.io/en/latest/api.html) — data/clock as inputs with pull-ups; REQ via an NPN; RDY optional on pin 4
- [Instructables — *Interfacing a Digital Micrometer to an Arduino*](https://www.instructables.com/Interfacing-a-Digital-Micrometer-to-a-Microcontrol/) — the widely-copied reference implementation
- [New Screwdriver — Arduino interface for the Mitutoyo SPC data port](https://newscrewdriver.com/2020/09/22/arduino-interface-for-mitutoyo-spc-data-port/) — REQ as open-drain; 0xFFFF preamble used for resync
- [Mitutoyo 959149 product data](https://www.microridge.com/shop/digital-interface-cables/mitutoyo-gage-cable-w-data-send/) — 1 m cable with data-send switch, 10-pin Digimatic plug
- [Mitutoyo 500-171-30 specification](https://www.testequity.com/product/575IE7120-500-171-30) — 0–6″/150 mm, 0.0005″/0.01 mm, SPC output
- Prior in-repo desk research: [`../igaging_35-065-U01/igaging_dataconnect_hardware_findings.md`](../igaging_35-065-U01/igaging_dataconnect_hardware_findings.md) §3 and [`../igaging_35-065-U01/igaging_protcol_research.md`](../igaging_35-065-U01/igaging_protcol_research.md) §5
