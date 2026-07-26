# STATUS — iGaging 35-065-U01 data port

**Last updated:** 2026-07-26. Start here; everything else is detail.

## Where this stands

The connector is **mapped**, the mic **responds** to stimulus, but the **measurement data has not
been decoded** and has never been observed on any pin.

## ⚠ Hardware access constraints — read first

**1. The mic is CLOSED by default. Treat re-opening as a last resort.** The read-head FPC
retaining-clip tabs broke during the §11.11 teardown, and the tape/glue repair **will not tolerate
much strain**. Another opening could take the unit out of service. Everything below is tagged
**[closed-case]** (doable through the Micro-USB breakout, which exposes all five pins with the case
shut) or **[needs board access]**. **Exhaust every [closed-case] avenue first**, then do *all*
remaining board work in one planned session with a written checklist — and reinforce the FPC while
it is open.

**2. Only ONE side of the board has ever been seen.** The MCU is an unmarked chip-on-board blob on
the **LCD side**, which cannot be reached — the LCD is soldered on and the assembly is glued into
the front cover; separating it means cracking the glass. So everything about the MCU side is
**inference from the battery side**, including:

- that the drivers are wired MCU-GPIO → 330 kΩ → MMBT3904 base with the collector on the pin,
- that pins 2/3 land on MCU inputs rather than being routed or gated on the hidden side,
- that there are no further components — the hidden side has never even been photographed.

None of that is overturned by anything known, but it is **not measured**. Where the topology is used
as an argument (e.g. the damage assessment below), it is supporting reasoning; the load-bearing
evidence is empirical.

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

## Leading open hypothesis: Mitutoyo Digimatic

*(An earlier revision of this file listed Digimatic as ruled out. **That was an error** — it leaned
on a generic pin mapping already known to be wrong for this unit. Retracted; see `review.md`
§10.3.)*

**For it:**
- **The pin count fits exactly.** Digimatic minimally needs REQ + CLK + DATA + GND. This unit has
  **three signal pins and two grounds**, and needs no VDD pin because it is self-powered (pin 1
  drew 0.0 mA). Three signals is precisely the requirement.
- **It resolves the two-drivers contradiction.** Q1/Q2 are two open-collector drivers but only one
  output pin has been identified. Digimatic predicts exactly two device outputs: CK and DATA.
- Desk research (`igaging_dataconnect_hardware_findings.md`) argues the same from the accessory
  hardware — **but that is unmeasured third-party inference, not evidence.** See `review.md` §11.

**Against it:**
- §11.15 measured **one output (pin 1) and two inputs (pins 2/3)**; Digimatic wants two outputs and
  one input. This is the strongest counter-evidence — but it is softer than it reads: driving a pin
  masks any device drive on it (only 2 of 4 unmasked cells were captured), and the 10 kΩ pull-ups
  used are within ~2× of what these weak drivers can sink, so a driven-but-weak pin could read as
  "held at the rail." See `review.md` §3.4 and §5.7a.

## Not yet known

- What carries the measurement data. No connector pin has shown it under any stimulus tried.
- Whether pin 1's assertion is a protocol signal or a "data ready" / button line.
- The true duration and internal structure of the pin-1 event — **every capture of it ends while
  it is still low.**
- The internal logic-rail voltage (still unmeasured; measure across C4/C5).
- Where Q2 goes. There are two open-collector drivers but only one identified output pin.

## Next experiments (ranked)

### [closed-case] — do all of these first

1. ~~**DMM through the breakout, battery out:** diode-test pins 1/2/3 to GND.~~ **DONE
   2026-07-26** — all open; shorted clamps ruled out, symmetry comparison did not run
   (`BENCH_LOG.md` §11.17). **Remaining half:** `python diode_test.py --mode resistance` to catch a
   leaky path that diode mode reports as OL.
2. **Estimate the internal rail without opening the mic:** hold the DATA button, clock pin 2, and
   **ramp the drive amplitude down** (3.0 → 2.5 → 2.0 → 1.5 → 1.2 → 1.0 → 0.8 V) until pin 1 stops
   strobing. A CMOS input threshold sits near **0.5 × V<sub>DD</sub>**, so a cut-off near 1.5 V
   implies a ~3 V rail and one near 0.8 V implies ~1.6 V. Then redo the key pull-up tests at the
   implied rail and at **100 kΩ** (all prior work used a blanket 3 V / 10 kΩ — `review.md` §5.7a).
3. **Capture the pin-1 event end to end** — trigger on its falling edge with the trigger at the
   far left, long enough to catch the rising edge; then walk a µs-scale window through it.
   Fix `read_raw` first (`:STOP` before reading — `review.md` §1.4).
4. **Deliver the documented waveform**: 21-cycle burst, 9 kHz, **20 % duty** (22 µs high / 89 µs
   low), idle LOW, into pin 2 then pin 3, gated from pin 1's falling edge. No test has ever used
   anything but a 50 % square.

### Purchases — recommended, not a last resort

5. **8-channel logic analyzer (~$15)** first. It removes the 1000-point-screen-read limitation that
   has distorted every result to date, and it is the right instrument for step 6 anyway.
6. **The `100-700-USB-MC` cable (~$70).**
   - **Step 0, before plugging anything in: ohm out the adapter cable.** Buzz all five micro-USB
     pins against all ten pins of the box-end 2×5. Five clean 1:1 connections ⇒ the cable is
     passive ⇒ **the complete micro-USB pinout falls out for free, including which pin is REQ.**
     Opens or diode drops ⇒ active electronics in the hood. Ten minutes, no power, no risk, either
     outcome informative.
   - Then sniff it **in-line**, so raw frames can be correlated against the exact decimal string
     its HID keyboard types — that settles framing *and* the counts-per-unit constant in one
     session. Dual-purpose: if the RE stalls, the cable *is* a working data-capture solution.

### [needs board access] — LAST, and only as one batched session

7. Do the whole checklist in a single opening (`review.md` §5.1), never for one item alone:
   ring **Q1/Q2 collectors** to pins 1/2/3 (resolves the two-drivers/one-output contradiction),
   trace the **`J10–J81` jumper matrix**, trace the **DATA button contacts** (in the reference
   Digimatic design the cable's data button is part of the port interface, not a private MCU
   input), measure the rail across **C4/C5**, and compare **Q1/Q2 in-circuit**. Reinforce the FPC
   while it is open.

> **Honest assessment.** Steps 1–2 are free information — do them. Steps 3–4 are the best remaining
> guesses, but a timed handshake has too many free parameters (sequence, timing, which pin, duty,
> gating) to brute-force reliably from outside; call it **~15–20 % combined**. Steps 5–6 are the
> only path with a guaranteed outcome, and five bench sessions in, ~$85 is cheap against the
> alternative. Step 7 is individually the highest-information work in the project but is gated
> behind a re-open that risks the unit — which is exactly why it now sits last rather than first.

## Was the port damaged by the over-drive? — probably not

§11.7 drove ~10 V into every pin for a session before the AWG High-Z bug was found (§11.8), and the
read-head FPC clip broke during teardown (§11.11). Both are on the record. **Neither is a likely
explanation for the current symptom**, for three reasons (full analysis in `review.md` §4):

- **~6 mA.** The 10 V EMF sat behind 50 Ω + the 1 kΩ series resistor; a pin clamping at ~3.7 V saw
  (10 − 3.7)/1050 ≈ 6 mA, inside the ±10–20 mA absolute-max clamp current typical of MCU inputs.
  Latch-up needs roughly an order of magnitude more and would have been obvious.
- **Topology** *(inference — see the access constraints above)*. The output path appears to be
  MCU → 330 kΩ → MMBT3904 base with the collector on the pin, which would mean **pin 1 never
  touches the die**; 10 V on a 3904 collector (V<sub>CEO</sub> 40 V) is a non-event. Read off the
  battery side only; the routing through the hidden side is not traced.
- **All three pins still work, measured *after* the over-drive** (§11.14/§11.15): pins 2/3 still
  receive edges, pin 1's driver still pulls hard low, the trigger logic still evaluates correctly.
  Damage would have to have spared all of that and killed only the data path.

The simpler explanation, consistent with everything: **the port is healthy and is waiting for a
timed handshake nobody has guessed.**

Caveat worth keeping: "the mic reads correctly" tests the LCD and encoder, **not** the port. The
real port health check is the §11.15 pin-1 response — and it passes.

**Checked 2026-07-26 (closed-case diode test, `BENCH_LOG.md` §11.17) — partial:** every signal pin
read **OL (open)** to ground in both directions, with the pin 4↔pin 5 sanity short confirming good
leads. That **rules out a clamp fused short** — the common over-voltage failure mode — on all three
pins. But with everything open there was no working-clamp baseline, so the intended pin-2-vs-pin-3
symmetry comparison never ran, and the test cannot distinguish healthy protection from destroyed
protection. **Still to do:** `python diode_test.py --mode resistance`, which measures into the MΩ
range and can see a leaky path that reads OL in diode mode.

A second micrometer is *not* worth buying for this — it controls for damage without revealing the
protocol.

## Files

| File | Purpose |
|---|---|
| `STATUS.md` | This — current state and next steps |
| `BENCH_LOG.md` | Chronological bench record (§11.1–§11.16) + remaining Phase B/C plans |
| `igaging_protcol_research.md` | Protocol reference: candidate families, specs, sources |
| `igaging_dataconnect_hardware_findings.md` | ⚠ **Unmeasured desk research**, written without knowledge of this project — a Digimatic hypothesis argued from vendor photos. Hypothesis, not evidence |
| `review.md` | Audit of the above against the raw captures — read before trusting a conclusion |
| `README.md` | What the device is |
| `ARCHIVE/` | Retired docs, superseded but kept for provenance |
| `*.py` | Bench tooling (`scpi_lib`, `psu_lib` + per-experiment scripts) |
| `captures/` | Raw scope captures (git-ignored) |
| `findings/`, `board_teardown/`, `PICT00*.jpg` | Milestone screenshots and teardown photos |
