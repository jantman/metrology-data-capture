# STATUS — iGaging 35-065-U01 data port

**Last updated:** 2026-07-26. Start here; everything else is detail.

## Where this stands

The connector is **mapped**, the mic **responds** to stimulus, but the **measurement data has not
been decoded** and has never been observed on any pin.

## Confirmed (this unit)

| | |
|---|---|
| **Pins 4 and 5** | **GND** — both, tied together and to battery negative |
| **Pin 1** | The mic's **only output**. Asserts a long (≥25 ms) LOW when triggered |
| **Pins 2 and 3** | **Inputs**, and symmetric — driving *either* works |
| **Trigger** | **DATA button held** *AND* **edges on pin 2 or pin 3.** Both required |
| **Supply** | Self-powered from the CR2032. **No rail on the connector**; pin 1 drew 0.0 mA when fed 3 V |
| **Idle** | All three signal pins float (~−0.02 V); no internal pull-ups |
| **Outputs** | Open-collector (Q1/Q2 = MMBT3904 + 330 kΩ base) → external pull-**ups** required |
| **Board** | `MD311-4.1A`, shared multi-SKU board with a `J10–J81` jumper matrix. MCU is an unreachable COB blob |

## Ruled out

- Free-running / self-clocked output (passive listening, with and without pull-ups).
- Pin 1 as a VDD input that powers the interface.
- Clock **rate** as the missing factor — pin 1's response is identical from 10 Hz to 9 kHz.
- **Digimatic/SPC** is now largely closed: the documented mapping puts REQ on pin 4 (ID), and
  pin 4 is hard-grounded here. See `review.md` §10.3.

## Not yet known

- What carries the measurement data. No connector pin has shown it under any stimulus tried.
- Whether pin 1's assertion is a protocol signal or a "data ready" / button line.
- The true duration and internal structure of the pin-1 event — **every capture of it ends while
  it is still low.**
- The internal logic-rail voltage (still unmeasured; measure across C4/C5).
- Where Q2 goes. There are two open-collector drivers but only one identified output pin.

## Next experiments (ranked)

1. **DMM only, board already accessible:** ring Q1/Q2 collectors, the `J10–J81` matrix, and the
   **DATA button contacts** to connector pins 1/2/3. Resolves the two-drivers/one-output
   contradiction and tests whether the button is part of the port interface.
2. **Measure the internal rail** across C4/C5, then redo the key pull-up tests at that voltage and
   at **100 kΩ** (all prior work used 3 V / 10 kΩ — see `review.md` §5.7a).
3. **Capture the pin-1 event end to end** — trigger on its falling edge with the trigger at the
   far left, long enough to catch the rising edge; then walk a µs-scale window through it.
   Fix `read_raw` first (`:STOP` before reading — see `review.md` §1.4).
4. **Deliver the documented waveform**: 21-cycle burst, 9 kHz, **20 % duty** (22 µs high / 89 µs
   low), idle LOW, into pin 2 then pin 3, gated from pin 1's falling edge. No test has ever used
   anything but a 50 % square.
5. **Buy the hardware — this is the recommended path, not a last resort.** An **8-channel logic
   analyzer (~$15)** first; it removes the 1000-point-screen-read limitation that has distorted
   every result to date and is the right instrument for step 6 anyway.
6. **The `100-700-USB-MC` cable (~$70).** Sniff it **in-line**, so raw frames can be correlated
   against the exact decimal string its HID keyboard types — that settles framing *and* the
   counts-per-unit constant in one session. It is also dual-purpose: if the RE stalls, the cable
   *is* a working data-capture solution.

> **Honest assessment of 3–4 vs 5–6.** Steps 1–2 are information-gathering and free; do them.
> Steps 3–4 are the best remaining guesses, but a timed handshake has too many free parameters
> (sequence, timing, which pin, duty, gating) to brute-force reliably from outside — call it
> ~15–20 % combined. Steps 5–6 are the only path with a guaranteed outcome. Five bench sessions in,
> ~$85 is cheap against the alternative.

## Was the port damaged by the over-drive? — probably not

§11.7 drove ~10 V into every pin for a session before the AWG High-Z bug was found (§11.8), and the
read-head FPC clip broke during teardown (§11.11). Both are on the record. **Neither is a likely
explanation for the current symptom**, for three reasons (full analysis in `review.md` §4):

- **~6 mA.** The 10 V EMF sat behind 50 Ω + the 1 kΩ series resistor; a pin clamping at ~3.7 V saw
  (10 − 3.7)/1050 ≈ 6 mA, inside the ±10–20 mA absolute-max clamp current typical of MCU inputs.
  Latch-up needs roughly an order of magnitude more and would have been obvious.
- **Topology.** The output path is MCU → 330 kΩ → MMBT3904 base, collector on the pin — so **pin 1
  never touches the die**, and 10 V on a 3904 collector (V<sub>CEO</sub> 40 V) is a non-event.
- **All three pins still work, measured *after* the over-drive** (§11.14/§11.15): pins 2/3 still
  receive edges, pin 1's driver still pulls hard low, the trigger logic still evaluates correctly.
  Damage would have to have spared all of that and killed only the data path.

The simpler explanation, consistent with everything: **the port is healthy and is waiting for a
timed handshake nobody has guessed.**

Caveat worth keeping: "the mic reads correctly" tests the LCD and encoder, **not** the port. The
real port health check is the §11.15 pin-1 response — and it passes.

**Cheap confirmation while the board is open:** diode-test pins 1/2/3 to GND and to the rail and
compare them; asymmetry between pins 2 and 3 is the thing to look for, since they should be
symmetric inputs. A second micrometer is *not* worth buying for this — it controls for damage
without revealing the protocol.

## Files

| File | Purpose |
|---|---|
| `STATUS.md` | This — current state and next steps |
| `BENCH_LOG.md` | Chronological bench record (§11.1–§11.16) + remaining Phase B/C plans |
| `igaging_protcol_research.md` | Protocol reference: candidate families, specs, sources |
| `review.md` | Audit of the above against the raw captures — read before trusting a conclusion |
| `README.md` | What the device is |
| `ARCHIVE/` | Retired docs, superseded but kept for provenance |
| `*.py` | Bench tooling (`scpi_lib`, `psu_lib` + per-experiment scripts) |
| `captures/` | Raw scope captures (git-ignored) |
| `findings/`, `board_teardown/`, `PICT00*.jpg` | Milestone screenshots and teardown photos |
