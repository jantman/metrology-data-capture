# STATUS — iGaging 35-065-U01 data port

**Last updated:** 2026-08-09. Start here; everything else is detail.

> **Bottom line: blind open-loop reverse engineering is finished on this unit.** 128 clock-injection
> combinations, all negative, with validated instrumentation (§11.20–§11.23). The remaining path is
> the `100-700-USB-MC` cable sniff, preceded by a ~$15 logic analyzer.

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
- **Open-loop clocking, BOTH directions, THREE rail voltages** — clock pin 2/watch pin 3 (§11.20),
  clock pin 3/watch pin 2 (§11.21), and the latter again at 1.8 V and 2.4 V rail+amplitude
  (§11.22). **96 combinations**, armed trigger on the watched pin, clock verified on the driven
  one, positive control every run. **The mic does not respond to an open-loop clock.** One
  variable still outstanding: the 10 kΩ pull-ups.
- **The button changing anything** — held vs released made no difference in any of the 64
  combinations, consistent with the mic's MCU not sensing it at all.
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

**Both arguments that favoured it have since been spent** (§11.19):

- ~~"The pin count fits exactly — three signal pins for REQ + CLK + DATA."~~ **Pin 1 is the
  button**, so only **two** signal pins remain. Digimatic needs three. This is now the decisive
  argument *against*.
- ~~"It resolves the two-drivers contradiction: Q1/Q2 = CK + DATA."~~ That contradiction is
  resolved differently and more simply — pin 1 is not driven by either transistor, so Q1/Q2 map
  onto pins 2 and 3 with no Digimatic required.
- The desk research in `igaging_dataconnect_hardware_findings.md` still argues for Digimatic from
  the accessory hardware, but that is unmeasured third-party inference written without knowledge
  of this unit (`review.md` §11).

Not formally impossible — one of the two remaining pins would have to be bidirectional — but it is
no longer the leading reading.

## Inference worth testing: Q1 and Q2 most likely drive pins 2 and 3

Not measured — flagged because it changes what to expect from step 2. The board has **two**
open-collector drivers (Q1/Q2, MMBT3904 + 330 kΩ base, §11.11). Pin 1 is now known to be a passive
switch, so it is **not** driven by either of them. That leaves pins 2 and 3 as the only candidates.

If that holds, **pins 2 and 3 are outputs as well as inputs** — the mic can pull either low — and
the long-standing "two drivers but only one output pin" contradiction dissolves. It also means the
role swap in step 2 matters: watch pin 2 while clocking pin 3, not just the reverse.

Ringing Q1/Q2's collectors to the connector pins is what would settle it, and that is now the main
reason to open the case (step 7).

## Not yet known

- **What carries the measurement data.** No connector pin has shown it under any stimulus tried.
- **Whether pin 2 can be driven by the mic** — never watched while pin 3 was clocked. Next step.
- **Whether the mic senses the button at all.** Pin 1 is a switch to ground; if it goes nowhere
  else, the MCU may be unaware of it and the button is purely a host-side signal. §11.20 saw no
  difference between button held and released, which is weak evidence for "unaware".
- **The internal logic-rail voltage.** Still unmeasured; the threshold-sweep method turned out
  invalid (§11.18) and no closed-case alternative exists. Needs C4/C5, i.e. board access.
- **Where Q1 and Q2 actually go** — inferred to be pins 2 and 3, never rung out.

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
   broken VMIN polling loop and §11.16 always triggered on pin 1, i.e. on the button.
   ~~**`interface_sweep.py`**, both role assignments~~ **DONE 2026-08-09 — BOTH NEGATIVE**
   (§11.20, §11.21). 64 combinations, positive control fired, clock verified every time: neither
   pin 2 nor pin 3 is ever pulled low. **Open-loop clocking is exhausted** — properly this time.
   ~~**Then: lower drive amplitudes.**~~ **DONE 2026-08-09 — negative at 1.8 V and 2.4 V**
   rail+amplitude (§11.22), which also removed the 3 V pull-up rail that had been forward-biasing
   the mic's input clamps in every test since §11.12.
   **→ NEXT, and now the only variable left: swap the pull-ups to 100 kΩ.** Q1/Q2's 330 kΩ base
   resistors cap their sink at ≈0.7 mA at a 3 V internal rail — but at 1.8 V that falls to
   ≈0.33 mA against the 0.3 mA a 10 kΩ pull-up demands, i.e. **right at the edge**. A weak driver
   would be masked *precisely* in the low-voltage runs just completed, so this is not an
   alternative to them — it is what makes them conclusive (`review.md` §5.7a).
3. **Redo the decisive tests at 100 kΩ** rather than 10 kΩ pull-ups (`review.md` §5.7a). Q1/Q2's
   330 kΩ base resistors cap the sink at ~0.7 mA against the 0.3 mA a 10 kΩ pull-up demands — only
   ~2× margin, so a weakly-driven pin could read as "held at the rail". Cheap insurance if step 2
   comes back negative.
4. ~~Capture the pin-1 strobe end~~ **DONE** (§11.18/§11.19) — it is a button contact, nothing
   further to learn. ~~Estimate the rail by sweeping the input threshold~~ **DOESN'T WORK** — the
   response was never gated on the driven input, so the method is invalid (§11.18/§11.19). **The
   internal rail remains unmeasured and there is currently no closed-case method for it.**

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
   ring **Q1/Q2 collectors** to pins 2/3 (see the inference below — this is now the main reason to
   open it), trace the **`J10–J81` jumper matrix**, check whether the **DATA button** also reaches
   an MCU pin or is *only* a switch to the connector, measure the rail across **C4/C5**, and
   compare **Q1/Q2 in-circuit**. Reinforce the FPC while it is open.

> **Honest assessment (revised after §11.19).** Step 2 is now the pivotal experiment and its odds
> are better than the old "~15–20 % for a blind handshake search", because the target has shrunk:
> the interface is two wires, not three, and the previous negatives on those two wires were all
> produced by instrumentation now known to be broken. Call it a genuine coin-toss rather than a
> long shot. Step 3 is cheap insurance on the same question.
>
> Steps 5–6 remain the only path with a *guaranteed* outcome and are still worth buying regardless
> — the logic analyzer especially, at ~$15, since the 1000-point screen read has distorted results
> throughout. Step 7 is the highest-information work but is gated behind a re-open that risks the
> unit, which is why it sits last.

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
| `interface_sweep.py` | **The current experiment** — automated search of pins 2/3 for a driven data line |
| `preflight.py` | Verifies the rig wiring before a long run; no button pressing needed |
| `diode_test.py` | Closed-case port health check (diode + resistance modes) |
| `button_only_capture.py`, `strobe_end_capture.py`, `button_switch_test.py` | The pin-1 characterisation that led to §11.18/§11.19 |
| `scpi_lib.py`, `psu_lib.py`, `dmm_lib.py` | Instrument clients (scope+AWG, B&K PSU, OWON DMM) |
| other `*.py` | Earlier per-experiment scripts, largely superseded |
| `captures/` | Raw scope captures (git-ignored) |
| `findings/`, `board_teardown/`, `PICT00*.jpg` | Milestone screenshots and teardown photos |
