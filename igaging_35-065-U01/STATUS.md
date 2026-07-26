# STATUS — iGaging 35-065-U01 data port

**Last updated:** 2026-07-26. Start here; everything else is detail.

## Where this stands

**The mic has never been observed to drive any connector pin.** Every apparent "device response"
recorded on 2026-07-26 was the **DATA button's switch contact** on pin 1 (§11.19, confirmed with
the battery out — a switch conducts unpowered, a transistor cannot).

The real interface is **two wires, pins 2 and 3, still undecoded** — plus the button on pin 1 as a
"user wants a reading now" signal to the host. That shape matches the **iGaging 21-bit protocol**
(host drives CLK, mic returns DATA) and argues against Digimatic, which needs three signals.

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
| **Pin 1** | The **DATA button's switch contact** to ground — NOT a device output (§11.19). Closed while held: ~155 ms on a tap, indefinitely on a hold |
| **Pins 2 and 3** | The **actual data interface**, still undecoded. Accept driven edges; never yet seen to drive |
| **The mic** | Has **never** been observed to drive any connector pin |
| **Supply** | Self-powered from the CR2032. **No rail on the connector**; pin 1 drew 0.0 mA when fed 3 V |
| **Idle** | All three signal pins float (~−0.02 V); no internal pull-ups |
| **Outputs** | Open-collector (Q1/Q2 = MMBT3904 + 330 kΩ base) → external pull-**ups** required |
| **Board** | `MD311-4.1A`, shared multi-SKU board with a `J10–J81` jumper matrix. MCU is an unreachable COB blob |
| **Separate nets** | Pins 1, 2, 3 are three **genuinely independent** nets — every pin-to-pin pair open both ways (§11.17b) |
| **Pins 4 ≡ 5** | Interchangeable as ground references — cross-checked at measurement level, not just continuity (§11.17b) |
| **Pin 1 ≠ pins 2/3** | Measured: pins 2/3 show ~30 MΩ to ground, pin 1 reads open. First electrical support for the inferred topology (§11.17b) |

## Ruled out

- Free-running / self-clocked output (passive listening, with and without pull-ups).
- Any transmission on pins 2/3 during a button press: with **no clock at all**, both inputs
  unmasked simultaneously for the first time, neither is ever pulled low (§11.18).
- Pin 1 as a VDD input that powers the interface.
- Clock **rate** as the missing factor — pin 1's response is identical from 10 Hz to 9 kHz.

## Leading hypothesis: the iGaging 21-bit protocol on pins 2/3

Two signal wires plus a button is exactly its shape — host drives CLK, mic returns DATA on the
other, and the button tells the host's MCU when to read. This is the original §3 hypothesis and it
now has a clean pin budget.

**This displaces Digimatic**, which needs REQ + CK + DATA = three signals; with pin 1 spent on the
button, only two remain. (The `review.md` §10.3 argument for Digimatic rested on a three-signal
count that §11.19 has now spent.)

## Superseded hypothesis: Mitutoyo Digimatic

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

1. ~~**DMM through the breakout, battery out:** port health check.~~ **DONE 2026-07-26**, both
   passes (`BENCH_LOG.md` §11.17/§11.17b). Damage ruled out; three separate signal nets confirmed;
   pins 4/5 verified interchangeable; pin 1 shown electrically distinct from pins 2/3.
2. **The properly-instrumented interface search — now FULLY AUTOMATABLE.** Because pin 1 is a
   switch, a button press can be synthesised by pulling pin 1 low, so no human is needed and runs
   can be long, repeated and unattended:
   ```
   AWG CH1 -> 1k -> pin 1     hold LOW = "button held"
   AWG CH2 -> 1k -> pin 2     the clock
   scope   -> pin 3           armed trigger on a FALLING edge = the mic driving DATA
   ```
   **No test has ever armed a trigger on a data pin during a clocked read** — §11.12 used the
   broken VMIN polling loop and §11.16 always triggered on pin 1, i.e. on the button. Sweep clock
   rate, **20 % duty** (never once delivered — `review.md` §5.5a), burst framing, and the pin 2 /
   pin 3 role swap.
3. ~~Capture the pin-1 strobe end~~ **DONE** (§11.18/§11.19): ~155 ms on a tap, indefinite on a
   hold — it is a button contact, so there is nothing further to learn from it.
4. **~~Estimate the internal rail by sweeping the input threshold~~ — DOESN'T WORK.** Attempted
   2026-07-26 and **void**: the response is not gated on the driven input at all, so ramping the
   drive amplitude proves nothing (§11.18). The rail remains unmeasured; a genuine closed-case
   method for it is still wanted. Separately, still worth doing: redo the key pull-up tests at
   **100 kΩ** rather than 10 kΩ (`review.md` §5.7a).

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

## Was the port damaged by the over-drive? — NO (closed to a low residual)

§11.7 drove ~10 V into every pin for a session before the AWG High-Z bug was found (§11.8), and the
read-head FPC clip broke during teardown (§11.11). Both are on the record. **Neither is a live
explanation for anything**, on four independent grounds:

- **Measured, 2026-07-26 (§11.17b):** pins 2 and 3 — supposedly symmetric inputs — show
  **30.140 MΩ and 29.999 MΩ** to ground, a **0.47 % match**, each reproducing to within 0.05 %
  across both ground references. Damaged inputs do not track each other that closely. No shorts on
  any pin in any direction.
- **~6 mA.** The 10 V EMF sat behind 50 Ω + the 1 kΩ series resistor; a pin clamping at ~3.7 V saw
  (10 − 3.7)/1050 ≈ 6 mA, inside the ±10–20 mA absolute-max clamp current typical of MCU inputs.
  Latch-up needs roughly an order of magnitude more and would have been obvious.
- **Topology** *(inference — see the access constraints above)*. The output path appears to be
  MCU → 330 kΩ → MMBT3904 base with the collector on the pin, which would mean **pin 1 never
  touches the die**; 10 V on a 3904 collector (V<sub>CEO</sub> 40 V) is a non-event. §11.17b now
  gives this *some* electrical support: pin 1 really does behave as a different kind of node from
  pins 2/3.
- **All three pins still work, measured *after* the over-drive** (§11.14/§11.15): pins 2/3 still
  receive edges, pin 1's driver still pulls hard low, the trigger logic still evaluates correctly.

The simple explanation, consistent with everything: **the port is healthy and is waiting for a
timed handshake nobody has guessed.**

Caveat worth keeping: "the mic reads correctly" tests the LCD and encoder, **not** the port. The
real port health check is the §11.15 pin-1 response — and it passes.

A second micrometer is *not* worth buying: it controls for damage, and damage is no longer the
question.

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
