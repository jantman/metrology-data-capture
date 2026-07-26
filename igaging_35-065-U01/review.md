# Documentation Review — iGaging 35-065-U01 reverse-engineering

**Date:** 2026-07-26
**Scope:** `README.md`, `PROTOCOL_RESEARCH.md`, `BRINGUP_PLAN.md`,
`claude_desktop_initial_investigation.md` (§0–§11.16), cross-checked against the bench tooling
(`*.py`) and the raw capture artifacts in `captures/`.

**Method:** every load-bearing empirical claim in the docs was traced back to (a) the script that
produced it and (b) the capture files it should have written. Where files exist, they were
re-analyzed independently. Findings below are labelled **[verified]** when confirmed against the
stored data, **[code]** when derived from reading the tooling, and **[analysis]** when it is a
reasoning/logic problem in the text itself.

---

## 0. Executive summary

The bench log is unusually honest and self-correcting — it repeatedly catches its own instrument
bugs and voids its own results, which is exactly right. But the review surfaced problems in three
tiers:

1. **Two conclusions are contradicted by the evidence they cite.** The §11.16 "byte-for-byte
   identical" reading-independence proof is not what the stored data shows, and §11.12's
   "external stimulation is exhausted / the mic never drives any pin" was a **false negative**
   that §11.14–11.16 silently overturned without ever retracting it or diagnosing why it failed.
2. **The single most important physical observation — the pin-1 event — has never actually been
   captured.** Every record of it ends while the pin is still low. Its duration, its end, and any
   fine structure inside it are unmeasured, and the sample resolution used to declare it
   "information-free" (50 µs/sample) is ~4.5× coarser than the protocol's own documented bit
   period.
3. **"Exhausted" is claimed several times for search spaces that are demonstrably not exhausted**,
   and the docs' conclusion ("blind RE has reached its limit; buy the cable") is premature —
   there is a concrete, cheap list of untried experiments in §5 below, several of which the docs
   themselves proposed and then never ran.

There is also a serious unexamined hypothesis: **the port may have been damaged.** §11.8 records
that every pin was driven at **>9.5 V** for an entire session against a 3 V part. That is never
listed as a candidate explanation for "the port strobes but never shifts data."

---

## 1. Critical — claims contradicted by the evidence

### 1.1 §11.16 "byte-for-byte IDENTICAL (0/1000 samples differ)" is false **[verified]**

The claim:

> captured pin 1's strobe at **0.065 mm** vs **24.698 mm** … The two pin-1 waveforms are
> **byte-for-byte IDENTICAL** (0/1000 samples differ; both a ~25 ms low, 1 edge).

Re-analysis of `captures/readingA_ch1.{bin,pre}` vs `captures/readingB_ch1.{bin,pre}`:

| Comparison | Result |
|---|---|
| Raw bytes differing | **931 / 1000** |
| Digitized at a 1.5 V threshold | 0 / 1000 |
| Digitized at a 0.5 V threshold | **155 / 1000** (121 vs 125 transitions) |
| Post-trigger V<sub>avg</sub> | A: −0.02 V, B: −0.02 V |
| Post-trigger V<sub>min</sub> / V<sub>max</sub> | A: −1.04 / +0.90 V; B: −0.82 / +0.90 V |
| Post-trigger RMS in 2.5 ms bins, A | 0.72 0.33 0.28 0.62 0.54 0.33 0.50 0.66 0.27 |
| Post-trigger RMS in 2.5 ms bins, B | 0.32 0.51 0.64 0.27 0.29 0.73 0.30 0.35 0.62 |

The waveforms are identical **only after being crushed to one bit at a 1.5 V threshold**. The
underlying records differ substantially, and the post-trigger region has a clear, time-varying
±0.7 V envelope whose bin-by-bin pattern is *different* between the two readings. That envelope is
never mentioned, never explained, and never analyzed.

Two consequences:

- The stated conclusion — *"pin 1 carries no measurement information — it is a pure fixed
  'data-ready' strobe … conclusively rules out the last hypothesis"* — **is not supported by this
  measurement.** It supports only the much weaker "pin 1's coarse 1-bit envelope at 50 µs
  resolution is the same at both readings."
- The ±0.7 V post-trigger activity is exactly what undersampled fast switching looks like. It may
  well be crosstalk from the injected clock (the historic coupling ratio ~0.2 × 3 V ≈ 0.6 V fits),
  but that was never checked, and it is the one place the data could be hiding.

### 1.2 The described "clean ~25 ms low" is a trigger artifact, not a measurement **[verified]**

In `readingA_ch1` and `readingB_ch1`, the low region is samples **501–999** — i.e. it begins
exactly at the trigger point (centre screen, `:TIMebase:MAIN:OFFSet 0`) and **runs to the end of
the record.** The pin is still low when acquisition stops.

The same is true of the §11.14 high-res claim ("one clean high→low edge and stays low **≥1.6 ms**"
at 3.2 ns/pt × 1 M pts = 3.2 ms window, trigger centred → 1.6 ms post-trigger). Both numbers are
just "half the record length."

**Nobody has ever observed the end of the pin-1 event.** Its true duration is unknown; "~10 ms"
(§11.14, from a wide screenshot), "~10 ms low strobe" (§11.15) and "~25 ms low" (§11.16) are three
mutually inconsistent figures for the same event, and the discrepancy is never reconciled. This
matters: a strobe whose length varies with the reading would itself be the data.

Fix: trigger on pin 1 **falling**, set `:TIMebase:MAIN:OFFSet` so the trigger sits at the far left,
and use a window long enough to contain the rising edge. Then bisect inward at high resolution.

### 1.3 §11.12's "exhausted / never drives any pin" was a false negative, never retracted **[verified + code]**

§11.12 concludes:

> **CONCLUSION — external stimulation is exhausted.** … clock on every pin (continuous + burst),
> … **DATA button pressed**, spindle moving — **the mic never actively drives any connector pin.**
> This is a comprehensive negative, not a pin-identification gap.

§11.15 then establishes that driving pin 2 *or* pin 3 while the DATA button is held makes pin 1 go
low. **That is precisely the §11.12 Test 2 configuration** (clock on pin 2 → pins 1 and 3 watched;
clock on pin 3 → pins 1 and 2 watched; button pressed throughout). §11.12 Test 2 should have caught
it and did not.

§11.14 explains the breakthrough as *"the trigger was the on-body DATA button — the one interaction
we'd never combined with the pull-up rig."* **That is factually wrong**: §11.12's own text says the
button was pressed during Test 1 *and* Test 2.

The real reason is a measurement-methodology defect, and it is never identified:

- `pullup_passive_monitor.py` monitors by polling `:MEASure:ITEM? VMIN` in a Python loop with a
  **10 ms** acquisition window; §11.12 reports **466 samples in 40 s** → ~11.6 queries/s →
  the scope's reported window covers roughly **12 % of wall-clock time**.
- `pullup_clock_capture.py` is worse: `win_ms = 4.0` → a **4 ms** window per query.
- If a ~25 ms strobe fires once per button press and the user presses ~40 times in 40 s, the strobe
  is present ~2.5 % of the time. Multiplied by ~12 % observation coverage, the expected number of
  detections in a 40 s run is well under one.

**A null result from this monitor is not evidence of absence.** Every "monitored N seconds while
pressing DATA, no dip" result in §11.8, §11.10 and §11.12 inherits this defect and should be
downgraded from "negative" to "inconclusive."

`BRINGUP_PLAN.md`'s status banner still leads with the §11.12 conclusion verbatim ("the mic never
actively drives any connector pin — only passive crosstalk, everywhere") — see §6.1.

### 1.4 The §11.12 pull-up capture files are all **zero bytes** — the primary negative has no artifact **[verified + code]**

```
captures/pullup_clk_cont_p1_ch{1..4}.bin    0 bytes
captures/pullup_clk_cont_p2_ch{1..4}.bin    0 bytes
captures/pullup_clk_cont_p3_ch{1..4}.bin    0 bytes
captures/pullup_clk_burst_p1_ch{1..4}.bin   0 bytes
captures/button_data_ch{1..4}.bin           0 bytes
```

The preambles claim `mode=2` (RAW), 10000 points; the payloads are empty.

**Root cause [code]:** `pullup_clock_capture.py` issues `:RUN` (line 73) and then calls
`scope.read_raw()` (line 108) **without ever stopping the scope.** Rigol DHO RAW-memory readback
requires the acquisition to be stopped. Every script that stops first —
`arm_single()` → `:SINGle` → `wait_stop()` → `read_raw()` (`clock_injection.py`,
`burst_capture.py`) — produced full 250 000-byte files. Every script that reads RAW while running
produced zero bytes. The correlation is exact.

This also explains, and is a much simpler explanation than, the §11.14 complaint that *"DHO814 RAW
multi-channel readback is INCONSISTENT — the same frozen capture read back as 10 k / 250 k / 1 M
points."* The docs concluded "use NORMal (1000 pts) instead," which is what has crippled every
subsequent decode attempt (see §1.5). **The RAW path is probably fine; it just needs `:STOP` before
the read and a settle delay.** Abandoning RAW for a 1000-point screen read was an over-correction
with large downstream cost.

### 1.5 The decode was declared impossible using a record 4.5× too coarse to see the bits **[verified]**

All the "decisive" 2026-07-26 captures (`readingA`, `readingB`, `readingA_clk2`, `req_p*_frame`)
have `xinc = 5.0E-5` — **50 µs/sample, 1000 points, 50 ms window**. The two-input captures are
20 µs/sample.

Against the project's own protocol reference (`PROTOCOL_RESEARCH.md`: ~9 kHz clock ⇒ **111 µs bit
period**; DATA valid 4.75 µs after the edge), a 50 µs sample interval gives ~2.2 samples/bit —
right at Nyquist, with no margin — and **cannot resolve anything faster.** A Digimatic-style burst
(the §11.13 hypothesis) or any burst faster than ~10 kHz is entirely invisible.

§11.14 states this limitation explicitly:

> The bits (if any) are **faster than the 1000-pt screen read resolves** at a 2 ms window — a
> decode capture needs a window/depth matched to the (still-unknown) bit rate with a reliable
> readout.

…and then §11.16, two sections later, uses exactly that unresolved readout to declare the decode
impossible and the investigation over. **§11.16 contradicts §11.14's own stated caveat and never
addresses it.**

---

## 2. Internal contradictions between sections

### 2.1 Two open-collector drivers (Q1, Q2) vs. one output pin — never reconciled

- §11.11: *"Q1, Q2 = MMBT3904 NPN, each fed by a 330 kΩ base resistor … **textbook
  open-collector output drivers**."*
- §11.13 leans on this: *"Board has **two open-collector drivers** (Q1/Q2) = the device's **CK +
  DATA** outputs (a host-clocked slave wouldn't need two OC drivers)."*
- §11.15/§11.16: *"**pin 1 = the mic's sole OUTPUT**; pin 2 and pin 3 = **INPUTS**."*

These cannot all be true. If there are two OC output drivers, either the second drives a connector
pin that was mis-classified, or it drives something else (the FPC/read-head, a backlight, an
internal node), or the jumper matrix routes it to a pad that is unpopulated on this SKU. **Nobody
ever rang out Q1's and Q2's collectors to the connector pins** — a five-minute continuity/diode
test on an already-open board that would settle it definitively. This is the highest-value untested
item in the whole project.

### 2.2 The `−0.7 V` "open-collector low" is not an open-collector low **[analysis]**

§11.14/§11.15 repeatedly describe pin 1 as *"actively driven LOW — hard, to ~−0.7 V
(open-collector)."* An NPN in saturation with its emitter at ground cannot pull a node **below**
ground; V<sub>CE(sat)</sub> is ≈ +0.1…+0.3 V. A −0.7 V level is a *forward diode drop below
ground* — which points at something quite different (a clamp/protection diode conducting, a ground
offset between the scope reference and the PSU return, probe/instrument offset, or ringing
undershoot).

Independently, the verified post-trigger **V<sub>avg</sub> is −0.02 V, not −0.7 V** (§1.1 table).
The −0.7 V figure comes from `VMIN`, a peak detector — the exact metric §11.12 itself warns about:

> **Lesson: trust VAVG for a DC level; VMAX/VMIN exaggerate noise.**

§11.14 then bases its headline claim on VMIN. The conclusion "pin 1 is driven" survives (a pin held
near 0 V against a 3 V pull-up must be driven), but **"hard to −0.7 V, open-collector" is not
established**, and the sub-ground excursion is an unexplained anomaly worth ~10 minutes with a
meter and a scope-offset check.

### 2.3 The same evidence class yields opposite conclusions for "is pin 1 VDD?"

- §11.8: *"VDD held 2.997 V — **no** sag, which is expected for a healthy CMOS input (nA
  quiescent), so **'no sag' neither confirms nor denies** pin1=VDD."* — correct reasoning.
- §11.12: *"pin 1 drew **0.0 mA** … → **pin 1 is NOT a VDD input** that powers the interface
  (retires the 'unpowered interface' hypothesis)."* — the same class of evidence, now treated as
  decisive.

Additionally, the B&K 169x current readout is also sourcing the three 10 kΩ pull-ups
(3 V / 10 kΩ = 0.3 mA each, ~0.9 mA total). A "0.0 mA" display on that supply therefore means
"below display resolution," not "zero" — and a sleeping/idle CMOS interface block draws far less
than the resolution anyway. **The VDD hypothesis was retired on evidence that cannot retire it.**
(It may still be false — §11.15's finding that pin 1 is an output is much stronger evidence — but
the stated reasoning is unsound and is now embedded in `BRINGUP_PLAN.md`'s banner.)

### 2.4 `PROTOCOL_RESEARCH.md` was never updated and now contradicts the bench log

| `PROTOCOL_RESEARCH.md` says | Bench log says |
|---|---|
| "**No REQ line.**" (listed under *high confidence*) | §11.13 builds an entire hypothesis on a REQ line |
| "DATA driver: 21-bit refs use weak **pull-DOWNs** (10–47 kΩ) … implies push-pull, defined-low idle" | §11.11: outputs are **open-collector**, pull-downs **mask** them |
| "the working pair is almost certainly **CLOCK = pin 2, DATA = pin 3**" | §11.15: **pin 1** is the sole output; 2 and 3 are inputs |
| "**pin 1 is effectively unused here**" | §11.15: pin 1 is *the* output pin |
| "Highest-value next bench test: burst … **with a 10–22 kΩ pull-down on pin 3**" | §11.11: a pull-down is precisely the thing that blinded every earlier test |

None of these carry a supersede note. The file is presented as a standing reference and is now
actively misleading. It needs the same "⚠ superseded — see §11.x" treatment that §4 of the
investigation doc received.

### 2.5 §2 of the investigation doc contradicts §11.3

§2 asserts as fact:

> The Micro-USB pins … carry **the mic's low-voltage supply rail** and its clock/data lines.
> … **Pressing DATA can drop/reset the whole USB bus.** A passive cable wires the host's 5 V VBUS
> onto the mic's ~1.5–3 V VDD…

§11.3 establishes there is **no supply rail on the connector at all** (battery+ rings to no
connector pin), and §11.8/§11.12 establish the DATA button drives nothing on the connector. The §2
mechanism is therefore not the mechanism, and the "resets the host USB bus" claim is unsourced and
now inconsistent with everything measured. It should be marked unverified/superseded rather than
left as a §0-adjacent safety fact.

### 2.6 §8 vs. `PROTOCOL_RESEARCH.md` vs. §11.13 on which cable to buy

- §8 recommends Amazon `B00IO0EH16` and Penn Tool `35-630-USB`, and says **"Do NOT buy"** the
  `100-700-USB` SPC cable.
- `PROTOCOL_RESEARCH.md` says the correct part is `100-700-USB-MC` and explicitly *"supersedes the
  guess in investigation §8"* — but **§8 itself was never annotated**, so a reader following the
  doc order gets the superseded advice.
- §11.13 then argues the Micro-USB port may in fact **be** Digimatic/SPC — in tension with §8's
  "SPC will not work on this mic."

Given the "definitive next step" in three documents is *buy a cable*, having three different
part-number recommendations across the doc set is a real hazard.

### 2.7 `BRINGUP_PLAN.md` contradicts itself within one file

The banner says the AWG raw-SCPI port is **5025**; §2's equipment table still says
`rigol-awg.jasonantman.com` (port **assumed 5555 — verify**), and §3's pre-flight step 1 still
instructs the reader to discover the port. Same for `:OUTPut:IMPedance INFinity` in §1, which the
banner and §11.8 both establish is a rejected command that mis-parses dangerously.

### 2.8 Section ordering and a missing results section

- In `claude_desktop_initial_investigation.md`, sections appear in the order
  **11.11 → 11.14 → 11.15 → 11.16 → 11.12 → 11.13**. A reader going top-to-bottom hits the
  "BREAKTHROUGH" before the tests it supersedes, then ends the document on the *stale* §11.12/§11.13
  conclusions ("injection EXHAUSTED", "buy the cable", "try the Digimatic hypothesis"). The last
  thing the file says is the thing that is no longer true.
- **§11.13 has no results.** It is a test plan for `req_capture.py` that ends with *"If this
  reveals device-clocked data… if silent across all three REQ pins + rates, the §11.12 conclusion
  stands."* No outcome is ever recorded. Yet §11.15 cites it as an established negative:
  *"drive-alone §11.13 … do nothing."* The artifacts (`req_p1_scope.png`, `req_p2_frame_*`,
  `req_p3_frame_*`, `req_p3_scr_*`) show the runs happened — the write-up is simply missing.
- The `board_teardown/` photo index is stranded at the end of §11.16 rather than in §11.11 where
  the teardown is described.

---

## 3. Overstated claims

### 3.1 "the entire no-rewire stimulus space is exhausted" (§11.8), "injection EXHAUSTED" (§11.12), "blind reverse-engineering has reached its limit" (§11.16)

Each of these was written before a subsequent section found something new by doing something not
in the "exhausted" set. The pattern has now repeated three times. Section 5 lists what is still
untried; it is not a short list.

§11.12 does contain an honest caveat (*"Not literally every permutation was run… but the 0 mA VDD
draw and the uniform silence make further permutations very low value"*) — that caveat turned out
to be wrong on both counts, and the two conclusions it qualifies are now known false.

### 3.2 "6/6 permutations" conflates pull-down-era and pull-up-era results **[verified]**

`BRINGUP_PLAN.md`'s banner claims *"every pin as clock in every CLK/DATA/VDD role assignment (6/6
permutations)"*, citing §11.9.

- §11.9's sweep used `pin_sweep.py`, which places a **10 kΩ pull-DOWN on the watched pin**
  (docstring line 13). §11.11 then established that a pull-down **masks an open-collector output**.
  So all six §11.9 results are invalid under the model the project subsequently adopted, and §11.11
  says exactly that — but the banner still cites them as a comprehensive negative.
- Only **5** sweep captures exist (`sweep_clk1_vdd2`, `clk1_vdd3`, `clk2_vdd3`, `clk3_vdd1`,
  `clk3_vdd2`); the sixth row (`clk2 / vdd1`) is annotated in the §11.9 table as *"from §11.8
  runs"* — i.e. a different rig, different conditions, back-filled into the table. That should be
  visible in the table, not just in a parenthesis.
- **The permutation sweep has never been repeated with pull-ups.** §11.12 Test 2 ran continuous
  clock on each of pins 1/2/3 with no VDD permutations, plus burst on pin 1 only.

### 3.3 "9 kHz … the clock *rate* is confirmed NOT the missing factor" (§11.16)

The tests behind this were **continuous** clocks. `PROTOCOL_RESEARCH.md` ranks *burst framing*
(21 cycles + ~7 ms gap) as the **#1 candidate cause** precisely because *"the mic may frame on the
gap and never start mid-stream."* Continuous 9 kHz does not test that. Ruling out "rate" is not
ruling out "framing."

### 3.4 "Both INPUT pins also checked unmasked at both readings" (§11.16) — only half the matrix has artifacts **[verified]**

The claim requires four conditions: {pin 2 unmasked, pin 3 unmasked} × {reading A, reading B}.
Stored captures:

| File | Clock on | Unmasked input observed | Reading |
|---|---|---|---|
| `readingA` | unknown | **only ch1 was saved** — ch2/ch3/ch4 absent | A |
| `readingA_clk2` | pin 2 (ch2 toggling) | pin 3 @ V<sub>min</sub> +2.57 V → 0 % hard-low ✓ | A |
| `readingB` | pin 3 (ch3 toggling) | pin 2 @ V<sub>min</sub> +2.48 V → 0 % hard-low ✓ | B |

Two of four cells are supported. The `readingA` run saved **only channel 1**, so whatever the
unmasked input did at reading A was not preserved. The conclusion is probably right, but the
document asserts more than the artifacts carry.

### 3.5 The §11.16 two-input table has three rows and two capture files — one run overwrote another **[verified + code]**

`two_input_capture.py` builds its filename as `twoin_clk{clk_pin}_req{req_pin}` (line 70) —
**`--req-volts` is not in the tag.** So the `--req-volts 0` and `--req-volts 3` runs on the same
pin pair write to the same files.

The surviving `twoin_clk2_req3_ch3` (the REQ pin) reads V<sub>avg</sub> = **+2.99 V** — i.e. this
is the **REQ-high** run. The REQ-low row in the §11.16 table has no surviving artifact.
Likewise `twoin_clk3_req2_ch3` shows 360 transitions in a 20 ms window = **9 kHz**, so this file is
the 9 kHz re-run, not the 2 kHz run listed in the table.

Same class of bug in `pin_sweep.py` (tag omits `--freq`/`--amp`) and `pullup_clock_capture.py`
(tag omits `--data-pin`, `--freq`).

### 3.6 The safety argument in §11.6 / `BRINGUP_PLAN.md` §1 contains a logical error **[analysis]**

> At ≤ 1.5 V you **cannot** overvoltage any pin. A **1.5 V-rail part *answers* a 1.5 V clock**, so
> … **if it stays silent at 1.5 V on all three pins, it isn't a 1.5 V part** — so ramping toward
> the 3 V battery ceiling can't overvoltage it.

The middle premise is false, and this project is the proof: the device stayed silent at every
voltage for reasons that had nothing to do with rail voltage (wrong pin roles, missing pull-ups,
missing button). Silence is not evidence about the rail. The practice was still safe — the series
resistor and the sub-1 mA clamp-current bound are independently sufficient — but the stated
justification should be removed or corrected, because it invites the same inference elsewhere.

(Note the irony: §11.8 later showed the pins were being driven at **>9.5 V** during the very
session this argument was protecting.)

---

## 4. The unexamined hypothesis: is the port damaged?

§11.8 records:

> a "3 V" clock was really **>9.5 V** at the pin (clipping the scope at every vertical scale) —
> ~3× over the 3 V battery ceiling.

For the whole of §11.7 (multiple hours: continuous clock on all three pins at five amplitudes each,
burst runs, button runs), every connector pin was driven at ~10 V through a 1 kΩ resistor. Against
a 3 V CMOS part that is roughly 6–9 mA of sustained clamp/diode current per pin — far above the
"< 1 mA paranoid case" the safety section budgeted for.

Additionally §11.11 records that the **read-head FPC retaining-clip tabs cracked off** during
teardown, requiring a tape/glue repair.

Neither event appears anywhere as a candidate explanation for the current symptom — *"the port
acknowledges (strobes) but never shifts data."* That symptom is entirely consistent with a
surviving MCU/LCD (both battery-powered, unexposed) and a damaged output stage or a damaged
input receiver.

**This should be an explicit open hypothesis**, because it changes the recommended next step: if
the port is damaged, buying the `100-700-USB-MC` cable will produce a confusing null result on
*this* unit, and the money is better spent on a second micrometer (which also gives a
known-good comparison unit — something the project has never had).

Cheap partial checks, in order:
1. Diode-test pins 1/2/3 to GND and to the internal rail with a DMM; compare the three. A blown
   clamp shows up as a shorted or missing diode drop.
2. Compare Q1 and Q2 in-circuit (base–emitter and collector–emitter drops). They are accessible.
3. Note that the mic's LCD reading being correct proves nothing about the port — the docs
   repeatedly use "mic reading correctly" as a health check for the *interface*, which it is not.

---

## 5. Missing / skipped experiments, ranked by (value ÷ effort)

These are things the documents either never considered, or proposed and then never ran.

### 5.1 Ring out Q1/Q2 collectors and the jumper matrix to the connector pins — **do this first**
Zero risk, no instruments beyond a DMM, board already accessible, and it resolves §2.1 (two OC
drivers vs. one output pin) plus tells you which jumper positions gate which pin. §11.11 explicitly
identifies the jumper matrix as *"selects which signals route to which Micro-USB pins"* and then
never traces a single one. If a bridged/open jumper is disabling the data output on this SKU, that
is the whole answer, and it is sitting on the bench right now.

### 5.2 Measure the internal logic rail across C4/C5 — **still open since §10, never done**
§10 lists it as *(pending)*; §11.2 notes *"DATA's high level, once it responds, reveals the rail
voltage"* — but pin 1 responds now, and the rail was still never measured. Everything about drive
levels, pull-up rail choice, and level-shifter selection depends on this number. The board has been
open twice since.

**Corollary never considered:** every pull-up test used a **3 V** rail. If the internal rail is
1.5 V or 1.8 V (the docs' own stated family range), a 3 V pull-up is over-driving the inputs and
back-feeding the part through its clamps — which could plausibly be *why* the inputs "do nothing."
Nobody tried 1.8 V pull-ups.

### 5.3 Actually capture the pin-1 event end-to-end
- Trigger pin 1 **falling**, timebase offset so the trigger is at the far left, window long enough
  to catch the rising edge → learn the true duration.
- Then trigger pin 1 falling and **walk a short window through the event** with
  `:TIMebase:MAIN:OFFSet` (or the zoom/delayed timebase) at 1–10 µs/div → look for fine structure.
- Repeat both at two very different readings. *That* is the reading-dependence test §11.16 meant to
  run.
- Fix the RAW readback (§1.4: `:STOP` before `read_raw`, then verify the returned point count)
  instead of living with 1000-point screen reads.

### 5.4 Get a logic analyzer — **never mentioned in any document**
The entire decode is currently blocked on scope-readout limitations (§1.4, §1.5). A ~$15 8-channel
sigrok/PulseView clone samples 3 pins at 24 MS/s continuously for seconds, with software triggers,
and would have made §11.14–11.16 trivial. Given the docs' recommended alternative is a **$70**
cable of uncertain compatibility, this is a strictly better first purchase. It is also the right
instrument for the eventual cable sniff.

### 5.5 Burst clock on an **input** pin, with pull-ups and the button — never once done **[verified]**
The capture inventory shows burst-mode was run with pull-ups on **pin 1 only**
(`pullup_clk_burst_p1`) — i.e. burst was only ever driven into the pin later identified as the
*output*. There is no `pullup_clk_burst_p2` or `_p3`, and §11.16's button-era work is all
continuous clocks.

So: **21-cycle burst @ 9 kHz + ~7 ms gap, into pin 2 or pin 3, with pull-ups and the DATA button**
— the exact experiment `PROTOCOL_RESEARCH.md` ranks #1 — has never been performed under the
conditions now known to be necessary. This is a one-line change to an existing script.

### 5.6 The two-input handshake is 3 cells of a large matrix, not "exhausted"
Run, per §11.16's table: {CLK 2, REQ 3 @ 0 V}, {CLK 2, REQ 3 @ 3 V}, {CLK 3, REQ 2 @ 0 V}. Never
run:
- {CLK 3, REQ 2 @ 3 V} — the missing fourth corner.
- **Phase-swept dual clocks.** §11.15 explicitly proposed *"sweep CLK/REQ role assignments **and
  phase**"* — but `two_input_capture.py` holds REQ as a **DC level** and has no phase parameter at
  all. The DG902 supports channel phase coupling; the planned experiment was never built.
- **REQ pulsed then CLK burst** (assert REQ low, wait, then deliver the burst) — the actual shape
  of every real SPC/DRO handshake. Dismissed in §11.16 as *"low-odds shots in the dark"* without
  being tried.
- Duty cycle other than 50 %, and clock amplitude below 3 V (all button-era tests used 3 V).

### 5.7 Characterize the trigger condition properly
Currently known: "DATA button held AND edges on pin 2 or pin 3." Never measured:
- Does pin 1 respond **once per press**, or repeatedly while held? Per input edge?
- What is the **latency** from button press (or from the input edge) to the pin-1 fall?
- Does the response require the button *edge* or the *held state*?
- What happens if input edges arrive **during** the strobe — is the strobe the device saying
  "clock me now"? (That is the standard meaning of a data-ready line, and it implies the clock must
  be delivered *inside* the low window — which no test has done: every run drove a free-running
  clock asynchronous to the strobe.)

**This last one is the most promising untested idea in the project** and is a natural
reinterpretation of everything §11.14–11.16 found: pin 1 = DRDY (device asserts when the button
requests a transmission); the host must then clock it. A free-running asynchronous clock would
never satisfy that. The fix is to trigger on pin 1 falling and *gate* the AWG burst from that
trigger — the DG902 supports external/triggered burst.

### 5.8 Try the Bluetooth kit as the sniff target
`README.md` names two adapters — `100-700-USB-MC` **and `35-BT28-MC`**. Every "next step" in every
document considers only the wired one. The BT module is a small board with the same tool-end
connector; it is often cheaper and easier to probe than a sealed control box. It is never mentioned
again after `README.md`.

### 5.9 Never tried: varying what the mic itself is doing
All button-era captures were with a static spindle. §11.10 ranked *"clock/listen while the spindle
MOVES"* as **#1 — DO THIS FIRST**; it appears only as an aside folded into the pull-up tests
(§11.11: *"press DATA and move the spindle during the window"*) and never as a controlled
experiment with the now-known working trigger. Also never varied: mm vs inch mode, ABS vs INC, a
freshly-zeroed vs offset reading. If the strobe or its timing changes with any of these, that is
information.

---

## 6. Documentation defects

### 6.1 `BRINGUP_PLAN.md` is stale and actively misleading

Its status banner is dated **2026-07-25** and states as current fact:

> **Result: the mic never actively drives any connector pin — only passive crosstalk, everywhere.**
> … **INJECTION EXHAUSTED** … **DEFINITIVE NEXT STEP: get the official iGaging `100-700-USB-MC`
> cable** … **BUT — try this first (see §11.13): the Mitutoyo Digimatic SPC hypothesis.**

All of that was overturned on 2026-07-26 (§11.14–11.16). The file is the entry point for the next
bench session and it points the reader at a test (`req_capture.py` REQ sweep) that has already been
run. Its §4 decision tree, §7 deliverables checklist (all boxes unchecked, including "AWG SCPI
reachable; port confirmed" which is definitively done), and §0 "what we already know" (pins 1/2/3
roles "unknown") are all superseded.

### 6.2 The bench log's own claim to be canonical is undermined by its ordering

§11 opens with *"Where this section conflicts with the assumptions in §4–§5, this section wins."*
Good — but within §11 there is no such rule, and §11.12/§11.13 (older, wrong) physically follow
§11.14–11.16 (newer, right). Recommend: renumber into chronological order, and give §11.12 and
§11.13 the same "⚠ superseded by §11.14–11.16" banner that §4 received.

### 6.3 Suspect numbers in §1

| Row | Value | Concern |
|---|---|---|
| Accuracy (spec) | 0.00015" | — |
| **Repeatability (spec)** | **0.0005"** | Repeatability *worse* than accuracy is not physically sensible for this instrument class; the manufacturer figure is almost certainly **0.00005"**. |

The §1 note *"the 0.00005" last display digit is below the instrument's real repeatability"*
depends entirely on that suspect number and is probably wrong as written.

### 6.4 Raw evidence is git-ignored

`.gitignore` excludes `igaging_35-065-U01/captures/`. Several load-bearing claims (§1.1, §3.4,
§3.5) can only be checked against those local files, and the two most decisive ones turned out to
be inaccurate. Given the small size of the 2026-07-26 captures (1000 bytes each), the handful of
milestone captures behind headline conclusions should be committed — the 250 kB RAW files can stay
ignored.

### 6.5 `findings/` holds only two PNGs

§11.14 cites `findings/2026-07-26_databutton_*.png` as the milestone evidence. Neither the
"~10 ms dense burst" wide screenshot nor the high-res RAW capture referenced in §11.14 is among
them, so the two mutually-inconsistent duration figures (§1.2) cannot be adjudicated from the
repo.

---

## 7. Tooling defects that affect published results

| # | File | Defect | Effect on results |
|---|---|---|---|
| 1 | `pullup_clock_capture.py:108` | `read_raw()` called while scope is in `:RUN` | **All §11.12 Test 2 capture files are 0 bytes** (§1.4). Fix: `:STOP` first, verify point count. |
| 2 | `pullup_passive_monitor.py`, `pullup_clock_capture.py`, `req_capture.py` | Poll-based `VMIN` monitoring covers ~4–12 % of wall-clock time | Every "monitored N s, no dip" negative is inconclusive, not negative (§1.3). Fix: arm a `NORMal`-sweep single-shot trigger and let the scope watch continuously. |
| 3 | `two_input_capture.py:70`, `pin_sweep.py:95`, `pullup_clock_capture.py:62-65` | Output tags omit the varying parameter (`--req-volts`, `--freq`, `--amp`) | Runs silently overwrite each other; §11.16's table has 3 rows and 2 files (§3.5). |
| 4 | `analyze_capture.py:82` `sample_data_on_clock` | Samples DATA **at** the clock edge index | `PROTOCOL_RESEARCH.md` documents DATA valid **4.75 µs after** the edge. Sampling at the transition is the worst possible instant. Needs a configurable sample delay. |
| 5 | `analyze_capture.py:85` `autocorr_period(maxlen=40)` | Cannot find a frame longer than 40 bits | The §11.13 Digimatic hypothesis is **52 bits** — the analyzer structurally cannot confirm the project's own live hypothesis. |
| 6 | `analyze_capture.py:39` `digitize()` | Threshold derived from global min/max | One noise spike (and pin 1 shows −1.04 V excursions) skews the threshold for the whole record. Use a percentile or a fixed rail-referenced threshold. |
| 7 | `analyze_capture.py:27` `load_channel()` | No guard for empty/missing `.bin` | Crashes on the 0-byte §11.12 captures and on `readingA` (ch1 only). |
| 8 | `clock_injection.py:95` `responded()` | Fires on `transitions ≥ 10 and vpp ≥ 0.3 V` | Measured crosstalk is ~0.75 Vpp and clock-synchronous — **the auto-detector would have declared "RESPONSE" on pure crosstalk.** `BRINGUP_PLAN.md` §4 describes it as if it discriminates. Results were saved by manual interpretation, not by the tool. |
| 9 | `req_capture.py:86`, `pullup_passive_monitor.py:66` | Print *"Digimatic-style SPC confirmed"* / *"real frame!"* on any triggered falling edge | Over-claiming in tool output feeds over-claiming in the log. A trigger is not a confirmation. |
| 10 | `scpi_lib.py:232` | High-Z check `if "E+3" not in rb and "E37" not in rb` | `"E+3"` also matches a `1.0E+3` (1 kΩ) readback, which would pass the guard. Should compare numerically against ≥1e30. |
| 11 | `igaging_decode.py` | `FRAME_BITS`/`SIGN_ENCODING`/`TICKS_PER_MM` still placeholders; `GROUND_TRUTH = {}` | Expected at this stage — noted only so it isn't mistaken for validated. |

---

## 8. Recommended action list

**Correct the record (no bench time):**
1. Retract/annotate §11.12's "exhausted / never drives any pin" conclusion and §11.16's
   "byte-for-byte identical" claim; state the actual resolution limit (50 µs/sample) alongside
   every 2026-07-26 conclusion.
2. Reorder §11.12/§11.13 before §11.14 and add supersede banners; write the missing §11.13 results.
3. Rewrite `BRINGUP_PLAN.md`'s banner and §0/§2/§3/§7 to the post-§11.16 state; fix the port-5555
   and `:OUTPut:IMPedance` leftovers.
4. Add supersede notes to `PROTOCOL_RESEARCH.md` (REQ, pull-down guidance, pin mapping) and to §2,
   §4, §8 of the investigation doc.
5. Fix the §1 repeatability figure, or mark it unverified.
6. Add "the port may have been damaged by the >9.5 V over-drive session (§11.8) and/or the FPC
   repair (§11.11)" as an explicit open hypothesis.

**Bench work, in order (all cheap, none require a purchase):**
7. DMM: ring Q1/Q2 collectors and the `J10–J81` matrix to connector pins 1/2/3 (§5.1); diode-test
   all three pins for over-drive damage (§4).
8. DMM/scope: measure the internal logic rail across C4/C5 (§5.2). Then repeat the key pull-up test
   at that rail voltage rather than 3 V.
9. Fix `read_raw` (`:STOP` first) and re-run one pin-1 capture to confirm full-depth RAW works
   again (§1.4).
10. Capture the pin-1 event end-to-end: true duration, then walk a µs-scale window through it at
    two very different readings (§5.3).
11. Gate a 21-cycle 9 kHz burst **from** the pin-1 falling edge into pin 2, then pin 3 (§5.7) —
    the "pin 1 is DRDY, clock it while it's low" model. This is the highest-value new experiment.
12. Burst + pull-ups + button on pins 2 and 3 (§5.5); the missing {CLK 3, REQ 2 @ 3 V} corner and a
    phase-swept dual drive (§5.6).

**Purchases, if 7–12 come up empty:**
13. An 8-channel logic analyzer (~$15) **before** the $70 cable (§5.4).
14. Then the cable sniff — but consider a second micrometer instead if step 7 suggests damage
    (§4), since it doubles as a known-good reference.

---

## 9. What holds up well

For balance, these conclusions are well-evidenced and should be treated as solid:

- **Pins 4 and 5 are GND; pins 1/2/3 are the signals; no rail is exposed on the connector** (§11.3)
  — multiple independent confirmations, consistent with everything since.
- **The AWG `:OUTPut:LOAD INFinity` → 1 Ω firmware trap** (§11.8) — found by query-only detection,
  fixed with a readback guard, and correctly used to void the affected results. Model behavior.
- **The probe 1×/10× and VTOP/VBASe-sentinel gotchas** (§11.9) — real, correctly diagnosed,
  correctly generalized into reusable guards.
- **Pin 1 is driven low by the device under (button + input edges)** (§11.14/§11.15) — the drive
  itself is unambiguous (a pin held near 0 V against a 3 V pull-up cannot be crosstalk), even
  though the "−0.7 V open-collector" characterization is wrong (§2.2).
- **Pin 1 does not respond to driving pin 1; pins 2/3 are symmetric** (§11.15) — clean, controlled,
  well-designed experiment.
- **The open-collector insight** (§11.11) — the pull-down/pull-up realization was the correct
  diagnosis of why two sessions of work were blind, and it is what produced the breakthrough.
