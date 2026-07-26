# Documentation Review — iGaging 35-065-U01 reverse-engineering

**Date:** 2026-07-26 (updated same day to cover `igaging_protcol_research.md`)
**Scope:** `README.md`, `PROTOCOL_RESEARCH.md`, `BRINGUP_PLAN.md`,
`claude_desktop_initial_investigation.md` (§0–§11.16), and `igaging_protcol_research.md`,
cross-checked against the bench tooling (`*.py`) and the raw capture artifacts in `captures/`.

> **File-layout note:** this review was written against the pre-restructure layout, and its
> filename references are preserved as historical record. `claude_desktop_initial_investigation.md`
> §11 is now **`BENCH_LOG.md`** (same §11.x numbering, chronologically reordered); that file plus
> `BRINGUP_PLAN.md` and `PROTOCOL_RESEARCH.md` now live in **`ARCHIVE/`**. Current entry point is
> **`STATUS.md`**.

> **Update note:** §§0–9 were written before `igaging_protcol_research.md` existed. That document
> is reviewed in **§10**, and the places where it changes an earlier finding are marked
> **[amended — §10]** inline. Nothing in §§1–4 was weakened by it; several items in §5 and §8 got
> sharper.

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

One event also goes unexamined throughout: **the >9.5 V over-drive session.** §11.8 records that
every pin was driven at **>9.5 V** for an entire session against a 3 V part, and that is never
listed anywhere as a candidate explanation for "the port strobes but never shifts data." It should
be named — but on analysis it is **not** a likely explanation (§4): the injected current was ~6 mA,
the board topology keeps pin 1 off the die entirely, and all three pins are demonstrably still
functional *after* the over-drive. Treat it as due diligence, not a leading hypothesis.

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

**[amended — §10]** `igaging_protcol_research.md` (2026-07-26) now supersedes most of this file
with better-sourced content, but does not say so, and the two files disagree on sign encoding
(one's vs two's complement) and on the DATA-line pull direction. Two overlapping protocol-research
documents with near-identical names is itself a hazard — see §10.6.

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

## 4. Was the port damaged by the over-drive? — worth logging, but unlikely

> **Revised 2026-07-26.** An earlier draft of this section called the damage hypothesis
> "arguably the most important missing hypothesis" and suggested buying a second micrometer over
> the official cable. **That was too strong.** Working through the board topology and the
> post-over-drive evidence puts it well under 10 % — and under ~5 % for the specific damage that
> would actually explain the current symptom.
>
> **RESOLVED 2026-07-26 (§4.3, `BENCH_LOG.md` §11.17b).** The bench check is done: pins 2 and 3
> match to **0.47 %** on their leakage to ground, reproducing across both ground references; no
> shorts anywhere; pin 1 measurably distinct as the topology predicts. **The damage hypothesis is
> closed to a low residual** and should not be carried as a live explanation. The section is kept
> for the reasoning and the record.

§11.8 records:

> a "3 V" clock was really **>9.5 V** at the pin (clipping the scope at every vertical scale) —
> ~3× over the 3 V battery ceiling.

For the whole of §11.7 — multiple hours, continuous clock on all three pins at five amplitudes
each, plus burst and button runs — every connector pin was driven from the AWG's ~10 V EMF.
Additionally §11.11 records that the **read-head FPC retaining-clip tabs cracked off** during
teardown, requiring a tape/glue repair. Neither event appears anywhere in the bench log as a
candidate explanation for the current symptom ("the port acknowledges but never shifts data"), and
both should at least be named.

### 4.1 Why it is nonetheless unlikely

**The current was inside normal absolute-max ratings.** The ~10 V EMF sat behind the AWG's 50 Ω
source impedance plus the 1 kΩ series resistor. A pin clamping at rail + diode (~3.7 V) therefore
saw **(10 − 3.7) / 1050 ≈ 6 mA**. Typical MCU absolute-max input clamp current is ±10–20 mA per
pin. That is "don't do this," not a blowout. Latch-up generally needs an order of magnitude more,
and would have announced itself as a hot part, a garbled LCD, or a flattened cell — none observed.

**The board topology probably shields the die.** Per §11.11 the output path is MCU GPIO →
**330 kΩ** → MMBT3904 base, with the **collector** on the connector pin. So:

- **Pin 1 would not connect to the MCU at all** — it lands on a 3904 collector, rated
  V<sub>CEO</sub> = 40 V / V<sub>CBO</sub> = 60 V. Ten volts there is a non-event.
- Only pins 2/3 would reach MCU inputs, and those are the pins that took the ~6 mA.

⚠ **This is inference, not measurement** — see §5.1a. Only the battery side of the board has ever
been observed; the MCU is an unreachable COB blob on the LCD side, so the routing *to* the base
resistors and the fate of pins 2/3 are read off the visible components rather than traced. Treat
this as supporting argument. The load-bearing evidence is the next paragraph, which is empirical.

**Decisive: all three pins demonstrably still work — *after* the over-drive.** §11.14/§11.15 show
that pins 2 and 3 still receive edges (either one triggers a response), that pin 1's output driver
still pulls hard low, and that the MCU's port logic still evaluates the button-plus-edge condition
correctly.

For damage to be the blocker it would have to have spared the input receivers, spared the output
driver, spared the trigger logic, and destroyed *only* the data-shifting function. Silicon damage
is not that selective.

The far simpler explanation — and the one consistent with every observation — is that **the port is
healthy and is waiting for a timed handshake that has not been guessed.** That is exactly what a
port designed to talk to exactly one proprietary cable looks like.

### 4.2 What this changes

- **Do not buy a second micrometer for this reason.** It is a diagnostic, not a solution: it
  controls for damage without revealing the protocol. Revisit only if §4.3 turns up something odd.
- **The `100-700-USB-MC` cable remains the recommended purchase** (§8). The risk of a confusing
  null on a damaged unit is small, and the cable is dual-purpose — if the RE stalls it *is* a
  working data-capture solution.
- `igaging_protcol_research.md` **F2** ("grounding or connecting the data pin … to a low-impedance
  'sink' can let the magic smoke out" on newer iGaging encoders) is a real warning worth heeding
  going forward, but it describes hard-grounding a driven output, which is not what happened here.

### 4.3 Cheap checks

**RUN 2026-07-26, both passes — damage ruled out. See `BENCH_LOG.md` §11.17 / §11.17b.**

*Diode pass:* every signal-pin reading came back OL; only the pin 4↔pin 5 sanity step showed its
known short. That ruled out a clamp fused short, but with no working-clamp baseline the intended
pin-2-vs-pin-3 comparison never ran. ⚠ The script's verdict that pass ("MATCHED → no evidence of
damage") **was a bug and is retracted** — an overload returns a ~1e9 sentinel, so `1e9 − 1e9 = 0.0`
read as a perfect match. Fixed.

*Resistance pass* (19 placements, both ground references, plus pin-to-pin for the first time):

- **Pins 2 and 3 read 30.140 MΩ and 29.999 MΩ to ground — a 0.47 % match**, each reproducing to
  within 0.05 % across both ground references. **This is the comparison that failed to run in the
  diode pass, and it passes.** Damaged inputs do not track each other that closely.
- **Pin 1 reads OL in every direction against both grounds** while the inputs conduct. Same leads,
  same meter, same range, same session — so pin 1 is the **internal control** proving the 30 MΩ is
  a real property of pins 2/3, not instrument leakage. It is also the first *measured* evidence
  that pin 1 is a different kind of node from pins 2/3, which supports §5.1a's inferred topology
  (without confirming the specific MMBT3904 arrangement).
- **All three signal pins are separate nets** — every pin-to-pin pair open both ways. The
  "pins 2/3 might be one net" concern that motivated this pass did not pan out, and the
  three-signal-pin count underpinning §10.3's Digimatic argument survives.
- **Pins 4 and 5 verified interchangeable** at measurement level, not just by continuity.

Diode mode saw none of this because a ~30 MΩ path would need ~30 kV to pass its ~1 mA test current.
The directionality (conducts GND→pin only) says junction, not resistor — a standard lower ESD clamp
seen well below its forward voltage.

**Conclusion: §4's damage hypothesis is closed to a low residual.** Nothing further needed here.

**Deferred to the batched opening (§5.1):** comparing Q1 and Q2 in-circuit, and diode-testing the
pins against the *internal rail* rather than ground.

Keep in mind throughout that "the mic reads correctly" tests the LCD and encoder, **not** the port —
the bench log repeatedly uses it as an interface health check, which it is not. The real port health
check is the §11.15 pin-1 response, and that one passes.

---

## 5. Missing / skipped experiments, ranked by (value ÷ effort)

These are things the documents either never considered, or proposed and then never ran.

> **⚠ Access constraint — read before ranking any of these.** The micrometer must be treated as
> **closed by default.** Opening it again costs real risk: the FPC retaining-clip tabs broke during
> the §11.11 teardown and the tape/glue repair **will not tolerate much strain**, so a re-open could
> take the mic out of service entirely. Every experiment below is therefore tagged
> **[closed-case]** (doable through the Micro-USB breakout, which exposes all five pins with the
> case shut) or **[needs board access]**. **Exhaust every [closed-case] item first**, then batch
> *all* remaining board work into a single planned opening — see §5.1.

### 5.1 Board-access work — **batch it into ONE opening, and do it last** **[needs board access]**
Individually these are the cheapest, highest-information tests in the project; collectively they
are gated behind a re-open that risks the FPC repair. So: **do not open the mic for any one of
them.** Write the full checklist first, do them all in one session, and reinforce the FPC while
it is open.

The checklist, when that day comes:
1. **Ring Q1/Q2 collectors to connector pins 1/2/3.** Resolves §2.1 — two open-collector drivers
   but only one identified output pin. Also confirms (rather than assumes) that pin 1 lands on a
   transistor collector rather than an MCU pin, which is currently an inference (§5.1a).
2. **Trace the `J10–J81` jumper matrix.** §11.11 identifies it as *"selects which signals route to
   which Micro-USB pins"* and then traces none of it. If a bridged/open jumper disables the data
   output on this SKU, that is the whole answer.
3. **Trace the DATA button's contacts** to Q1/Q2 and to pins 1/2/3 (§10.5). In the reference
   Digimatic design the cable's data pushbutton is part of the port interface, not a private MCU
   input.
4. **Measure the internal logic rail across C4/C5** (see §5.2 — but try the closed-case estimate
   first).
5. **Compare Q1 and Q2 in-circuit** (base–emitter, collector–emitter) for over-drive damage (§4.3).

### 5.1a Everything about the MCU side is inference, not observation
**Partly corroborated 2026-07-26:** §11.17b measured pin 1 as electrically distinct from pins 2/3
(open vs ~30 MΩ to ground, with pin 1 as its own internal control). That is independent support for
"pin 1 is not an MCU pin" — though it confirms only the *class* of node, not the specific
MCU → 330 kΩ → MMBT3904 arrangement, which remains inference.

§11.11 records that the controller is an unmarked COB blob on the **LCD side, which cannot be
reached** — the LCD is soldered and the assembly glued into the front cover. So the accessible
(battery) side is the *only* side ever observed.

That means the following are **plausible readings of the visible components, not measurements**:

- "MCU-GPIO → 330 kΩ → NPN base, collector = output pin, emitter = GND" (§11.11). The base-resistor
  and transistor packages are visible; the connection *to the MCU* runs through the hidden side.
- That pins 2/3 land on MCU inputs directly, rather than being routed through the hidden side or
  gated by the jumper matrix.
- That there are no additional components — the hidden side has never been photographed.

This does not overturn anything, but it should be stated wherever the topology is used as an
argument. In §4 in particular, the topology reasoning is *supporting* inference; the load-bearing
evidence there is empirical (all three pins still work after the over-drive). Checklist item 5.1.1
is what would convert the inference into a measurement.

### 5.2 The internal logic rail — **estimate it closed-case first** **[closed-case]**
Still unmeasured since investigation §10 marked it *(pending)*; everything about drive levels,
pull-up rail choice, and level-shifter selection depends on it. But a direct measurement across
C4/C5 needs the board open (§5.1), so try the indirect route first:

**Sweep the input threshold.** Pin 1's strobe is a reliable, repeatable response to (button + edges
on pin 2 or pin 3). So hold the button, drive pin 2 with the clock, and **ramp the drive amplitude
down** — 3.0, 2.5, 2.0, 1.5, 1.2, 1.0, 0.8 V — recording the amplitude at which pin 1 stops
responding. A CMOS input threshold sits near **0.5 × V<sub>DD</sub>**, so a cut-off near 1.5 V
implies a ~3 V rail, and a cut-off near 0.8 V implies ~1.6 V. That is a usable estimate obtained
entirely through the breakout, with no risk, using tooling that already exists.

**Corollary never considered:** every pull-up test used a **3 V** rail. If the internal rail is
1.5 V or 1.8 V (the docs' own stated family range), a 3 V pull-up is over-driving the inputs and
back-feeding the part through its clamps — which could plausibly be *why* the inputs "do nothing."
Nobody tried 1.8 V pull-ups. The threshold sweep above settles which case you are in.

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

### 5.5a Clock **duty cycle** has never been varied — every test used 50 % **[verified, new — §10]**

`igaging_protcol_research.md` §4.2 specifies the 21-bit clock as **20 % duty: 22 µs high, 89 µs
low, idle LOW**, sourced to `SCALE_CLK_DUTY 20` in the canonical Arduino-DRO implementation. That
is a *narrow high pulse*, not a symmetric square.

Every clock this project has ever produced was **50 % duty**: `scpi_lib.Awg.square()` defaults to
`duty=50`, `clock_injection.py` defaults `--duty 50`, and `burst_capture.configure_burst()` never
issues `:SOURce1:FUNCtion:SQUare:DCYCle` at all — so even the burst trains were 50 %. No document
ever lists duty cycle as a variable.

If the receiver latches on a short high pulse or times its internal sampling from the falling edge,
a 50 % clock at 9 kHz presents a 55 µs high time where the reference implementation presents 22 µs.
This is a one-parameter change to existing tooling and belongs in the same run as §5.5's burst test.

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

### 5.7a The 10 kΩ pull-up may be too strong for this board's drivers **[new — §10]**

`igaging_protcol_research.md` F5/§4.1 recommends **~100 kΩ** pull-ups ("the lines behave as
open-drain/weakly-driven"; Yuriy: *"Pulling the lines to Vcc using a pair of 100 kOhm resistors did
the trick"*). Every bench test in this project used **10 kΩ** — ten times stronger.

Combine that with §11.11's own board observation and it becomes a live concern. Q1/Q2 are MMBT3904
NPNs fed through **330 kΩ** base resistors, so with a 3 V drive the base current is
(3 − 0.7)/330 kΩ ≈ **7 µA**, and at a typical h<sub>FE</sub> ≈ 100 the collector can sink at most
≈ **0.7 mA** before leaving saturation. A 10 kΩ pull-up to 3 V demands **0.3 mA** — the same order
of magnitude. The margin is roughly 2×, not the 20–50× you would normally want.

Two consequences:

- Pin 1's observed low is not a clean V<sub>CE(sat)</sub>, which fits §2.2's finding that the
  "−0.7 V open-collector low" is not behaving like a saturated NPN.
- More importantly, **§11.16's "pin 2 / pin 3 → 0 % hard-low" verdict assumed the pull-up was weak
  enough not to overpower a driver.** If either input pin is also (weakly) driven — the unresolved
  Q1/Q2-vs-one-output contradiction in §2.1 — a 10 kΩ pull-up could hold it well above the
  "hard-low" threshold while it is being driven. The negative is softer than stated.

Re-run the key pull-up tests at **100 kΩ** (and ideally at the measured internal rail, §5.2) before
treating any "held at the rail" result as final.

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
| 4 | `analyze_capture.py:82` `sample_data_on_clock` | Samples DATA **at** the clock edge index | `PROTOCOL_RESEARCH.md` says DATA is valid **4.75 µs after** the edge; `igaging_protcol_research.md` §4.2 says **~2 µs after the *falling* edge** (and see §10.4 — that 2 µs derivation looks like an arithmetic slip for ~4 µs). Either way, sampling *at* the transition is the worst possible instant, and the analyzer needs a configurable post-edge delay **and** an edge-polarity choice. |
| 5 | `analyze_capture.py:85` `autocorr_period(maxlen=40)` | Cannot find a frame longer than 40 bits | The §11.13 Digimatic hypothesis is **52 bits** — the analyzer structurally cannot confirm the project's own live hypothesis. |
| 6 | `analyze_capture.py:39` `digitize()` | Threshold derived from global min/max | One noise spike (and pin 1 shows −1.04 V excursions) skews the threshold for the whole record. Use a percentile or a fixed rail-referenced threshold. |
| 7 | `analyze_capture.py:27` `load_channel()` | No guard for empty/missing `.bin` | Crashes on the 0-byte §11.12 captures and on `readingA` (ch1 only). |
| 8 | `clock_injection.py:95` `responded()` | Fires on `transitions ≥ 10 and vpp ≥ 0.3 V` | Measured crosstalk is ~0.75 Vpp and clock-synchronous — **the auto-detector would have declared "RESPONSE" on pure crosstalk.** `BRINGUP_PLAN.md` §4 describes it as if it discriminates. Results were saved by manual interpretation, not by the tool. |
| 9 | `req_capture.py:86`, `pullup_passive_monitor.py:66` | Print *"Digimatic-style SPC confirmed"* / *"real frame!"* on any triggered falling edge | Over-claiming in tool output feeds over-claiming in the log. A trigger is not a confirmation. |
| 10 | `scpi_lib.py:232` | High-Z check `if "E+3" not in rb and "E37" not in rb` | `"E+3"` also matches a `1.0E+3` (1 kΩ) readback, which would pass the guard. Should compare numerically against ≥1e30. |
| 11 | `igaging_decode.py` | `FRAME_BITS`/`SIGN_ENCODING`/`TICKS_PER_MM` still placeholders; `GROUND_TRUTH = {}` | Expected at this stage — noted only so it isn't mistaken for validated. **[amended — §10]** `SIGN_ENCODING = "ones"` should now default to `"twos"`: `igaging_protcol_research.md` F8 resolves the long-standing dispute with a code citation (sign-extension `v |= 0xFFF00000`), which is two's complement, not one's. |
| 12 | `scpi_lib.py:244` `square()`, `burst_capture.py:32` `configure_burst()` | Duty cycle is fixed at 50 %; `configure_burst` never issues `:…:SQUare:DCYCle` at all | The reference 21-bit clock is **20 % duty** (§5.5a). No test has ever delivered the documented waveform shape. |

---

## 8. Recommended action list

**Correct the record (no bench time):**
0. Add a "see bench log §11" banner to `igaging_protcol_research.md` §0, strip the stray
   `</content>`/`</invoke>` markup at EOF, and resolve the two-protocol-research-files situation
   (§10.4, §10.6).
1. Retract/annotate §11.12's "exhausted / never drives any pin" conclusion and §11.16's
   "byte-for-byte identical" claim; state the actual resolution limit (50 µs/sample) alongside
   every 2026-07-26 conclusion.
2. Reorder §11.12/§11.13 before §11.14 and add supersede banners; write the missing §11.13 results.
3. Rewrite `BRINGUP_PLAN.md`'s banner and §0/§2/§3/§7 to the post-§11.16 state; fix the port-5555
   and `:OUTPut:IMPedance` leftovers.
4. Add supersede notes to `PROTOCOL_RESEARCH.md` (REQ, pull-down guidance, pin mapping) and to §2,
   §4, §8 of the investigation doc.
5. Fix the §1 repeatability figure, or mark it unverified.
6. Record the >9.5 V over-drive (§11.8) and the FPC repair (§11.11) as named events with a
   *low* assessed damage risk and the reasoning why (§4) — not as a leading hypothesis.

**Bench work — [closed-case] only, in order (no purchase, no opening the mic):**
7. DMM through the breakout, battery out: diode-test pins 1/2/3 to GND and compare the three.
   **Asymmetry between pins 2 and 3 is the signal** (§4.3).
8. Estimate the internal rail by **sweeping the input threshold** — hold the button, clock pin 2,
   and ramp the amplitude down until pin 1 stops strobing; the cut-off is ≈ 0.5 × V<sub>DD</sub>
   (§5.2). Then repeat the key pull-up tests at the implied rail rather than a blanket 3 V.
9. Fix `read_raw` (`:STOP` first) and re-run one pin-1 capture to confirm full-depth RAW works
   again (§1.4).
10. Capture the pin-1 event end-to-end: true duration, then walk a µs-scale window through it at
    two very different readings (§5.3).
11. Gate a 21-cycle 9 kHz burst **from** the pin-1 falling edge into pin 2, then pin 3 (§5.7) —
    the "pin 1 is DRDY, clock it while it's low" model. This is the highest-value new experiment.
    Deliver it at the **documented waveform**: 20 % duty, 22 µs high / 89 µs low, idle LOW (§5.5a).
12. Burst + pull-ups + button on pins 2 and 3 (§5.5); the missing {CLK 3, REQ 2 @ 3 V} corner and a
    phase-swept dual drive (§5.6). Repeat the decisive pull-up tests at **100 kΩ** rather than
    10 kΩ (§5.7a).

**Purchases, once 7–12 are exhausted — recommended, not a last resort:**
13. An 8-channel logic analyzer (~$15) **before** the $70 cable (§5.4) — now independently
    recommended by `igaging_protcol_research.md` §7.3. It removes the readout limitation that has
    distorted every result to date and is the right instrument for step 14 anyway.
14. **Cable session, step 0 — ohm out the adapter cable before plugging anything in** (§11.2):
    buzz all five micro-USB pins against all ten 2×5 pins. Five clean 1:1 connections ⇒ passive
    cable ⇒ the complete micro-USB pinout including REQ, for free. Then the sniff —
    **in-line**, per `igaging_protcol_research.md` §7: because the control
    box is a USB HID keyboard, you can correlate each captured raw frame against the exact decimal
    string it types, which settles framing *and* the counts-per-unit constant in one session. The
    bench docs' "sniff the cable" plan never noted this.
15. A second micrometer is **not** recommended — it controls for damage without revealing the
    protocol, and §4 puts the damage risk low. Reconsider only if step 7's diode tests come back
    asymmetric between pins 2 and 3.

**[needs board access] — LAST, and only as one batched session:**
16. Everything in §5.1's checklist at once: ring Q1/Q2 collectors and the `J10–J81` matrix to the
    connector pins, trace the DATA button's contacts (§10.5), measure the rail across C4/C5,
    compare Q1/Q2 in-circuit. **Do not open the mic for any single one of these** — the FPC repair
    will not tolerate much strain, and a re-open risks the unit. Write the checklist first, and
    reinforce the FPC while it is open.

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

---

## 10. Review of `igaging_protcol_research.md` (added 2026-07-26)

**Overall: this is the strongest document in the directory.** It is better sourced, better
calibrated about its own uncertainty, and it resolves two questions the older research left open.
It has one structural flaw — it is written as though the bench work does not exist — and a handful
of small errors.

### 10.1 What it does notably well

- **Confidence-ranked findings (★☆ scale) with the reasoning for each rank.** F7 is explicitly held
  at three stars with its own three counter-arguments listed. This is the right shape for research
  that will be acted on with a soldering iron.
- **Source-independence auditing.** It notices that the Instructables author (`sspence`) and the
  Hobby-Machinist poster are **the same person**, and downgrades "two corroborating sources" to
  one. It also notes Alex Whittemore *never published a capture* — he abandoned the breakout before
  taking timing. Both are exactly the kind of check `PROTOCOL_RESEARCH.md` did not do, and both
  materially change how much weight the 21-bit hypothesis deserves.
- **F8 resolves the one's-vs-two's-complement dispute** that `PROTOCOL_RESEARCH.md` explicitly
  punted on (*"sources conflict; resolve on bench"*). It does so correctly and by the right method:
  citing the canonical implementation's sign-extension (`v |= 0xFFF00000`) rather than the prose,
  and diagnosing "one's compliment" as long-propagated loose wording. Verified — that code is
  textbook two's-complement sign extension.
- **F9's counts-per-unit candidate table is a genuine contribution.** I checked all nine numbers:
  102 400/in → 4031.50/mm, 0.2480 µm, +0.04 %; 4000/mm → 101 600/in, 0.2500 µm, −0.74 %;
  4096/mm → 104 038/in, 0.2441 µm, +1.64 %. All correct. Turning "≈4030" into three testable
  hypotheses with a 0.05 % discrimination criterion converts Phase C from "measure a constant" into
  "decide between two designed values," which is a much stronger experiment.
- **§3's discrimination table** is the single most useful half-page: a set of observations that each
  map to one protocol family. See §10.3 — applied to this unit's data it produces a real result.
- **The mini-B pinout inversion trap** (F4) and the wire-colour warning (F3) are the kind of
  practical landmine that only shows up in this sort of survey.
- **The in-line cable-sniff insight** (§7): because the box is a HID keyboard, raw frames can be
  correlated against the typed decimal string. Three documents recommend sniffing the cable; only
  this one notes *why* it settles the scale factor too.

### 10.2 The structural flaw: it does not know about the bench log

The document never cites `claude_desktop_initial_investigation.md` §11, and several of its
higher-confidence claims are already **falsified on this specific unit**:

| Claim | Rank | Status on this unit |
|---|---|---|
| F4: pin 1 = VDD (supply into the tool) | ★★★★☆ | §11.12: solid 3 V on pin 1 drew **0.0 mA** and changed nothing; §11.15: pin 1 is the mic's **output** |
| F4/§4.1: pin 3 = DATA, driven by the tool | ★★★★☆ | §11.15: pin 3 is an **input**; driving it (+ button) makes pin 1 assert |
| F4/§4.1: pin 2 = CLK into the tool | ★★★★☆ | Half-right: pin 2 *is* an input, but so is pin 3, and they are symmetric |
| §0: "mic shifts out 21 bits on D+" | stated as the single most likely answer | §11.16: **no** connector pin carries measurement data under any stimulus tried |
| §7 step 3: passive capture while moving the spindle | procedure | Already done (§11.4, §11.12 Test 1) — negative |
| §10 open Q6: "whether the tool needs external VDD at all" | open | Already answered: no (§11.12, 0 mA) |

None of this makes the document wrong as *research* — it is an accurate survey of what the
community has published. But §0's executive summary asserts the conclusion far more confidently
than §2's own star ratings support, and a reader who starts at §0 and stops there will rebuild a rig
this project has already run three times. **§0 needs a banner pointing at §11 of the bench log.**

### 10.3 ⚠ RETRACTED — §3 does *not* kill the Digimatic hypothesis (my error)

> **This subsection was wrong and is retracted.** I argued that because the documented mapping puts
> Digimatic's REQ on micro-USB pin 4 (ID), and §11.3 measured pin 4 hard-grounded, this unit cannot
> be Digimatic. **That inference is unsound**, for a reason visible in this very review: the pin-4
> assignment comes from `igaging_protcol_research.md`'s generic iGaging mapping — **the same mapping
> §10.2 shows is already falsified on this unit** (it says pin 1 = VDD and pin 3 = tool-driven DATA;
> both are wrong here). You cannot rule out a protocol using a pin assignment from a mapping you
> have just demonstrated does not apply.
>
> **Our own data actually fits Digimatic better than I allowed.** This unit has **three signal pins
> plus two grounds**. Digimatic minimally needs REQ + CLK + DATA + GND — and **VDD is unnecessary
> here because the mic is self-powered** (pin 1 drew 0.0 mA, §11.12). Three signals is exactly the
> requirement. The REQ pin simply isn't pin 4; with pin 1 not being VDD, the whole generic mapping
> shifts.
>
> **And it resolves §2.1.** Two open-collector drivers (Q1/Q2) with only one identified output pin
> is precisely what Digimatic predicts: Q1 and Q2 = the device's CK and DATA outputs.
>
> **The counter-evidence is real but soft.** §11.15 found one output (pin 1) and two inputs
> (pins 2/3); Digimatic wants two outputs and one input. But that conclusion carries the caveats
> already documented here — driving a pin masks any device drive on it (§3.4: only 2 of 4 unmasked
> cells have artifacts), and the 10 kΩ pull-ups are within ~2× of what these weak drivers can sink
> (§5.7a), so a driven-but-weak pin could read as "held at the rail."
>
> **Corrected status: Digimatic is OPEN, and arguably the leading hypothesis** — not "largely
> closed." This retraction stands on our own measurements; it does not depend on
> `igaging_dataconnect_hardware_findings.md` (§11), which is desk research.

The original (incorrect) argument is preserved below for the record.

#### Original text — superseded

The document's own discriminator table says:

> | ID pin (4) measures 0 Ω to GND | 21-bit family (ID is grounded) |
> | ID pin (4) floats / sits near VDD with a pull-up | Possibly REQ → Digimatic |

and §5.1/§7 place Digimatic's **REQ on the ID pin (pin 4)**, calling it "a decisive discriminator
you can check with a meter."

**That meter check was done on 2026-06-21.** §11.3: *"Pins 4 and 5 are both GND — direct continuity
between them and to battery negative."* Pin 4 is hard-grounded.

So, by this document's own decisive criterion, **this unit is in the 21-bit family and is not
Digimatic** — and §11.13's Digimatic hypothesis, which `BRINGUP_PLAN.md`'s banner still recommends
trying first, is substantially weakened. It gets worse: `req_capture.py` drove REQ on pins **1, 2
and 3** — never on pin 4, the only pin the documented mapping puts REQ on, and a pin where the test
is impossible because it is tied to ground. **§11.13 never tested the hypothesis it was written to
test.**

This also resolves the §2.6 cable-recommendation tangle in favour of the micro-USB-native
`100-700-USB-MC`, and it means the §11.13 reasoning ("two OC drivers = the device's CK + DATA")
needs another explanation — see §2.1, still unreconciled and still answerable with a DMM.

Note the document contains a small internal tension here: F4 says pin 4 is grounded on iGaging
micro-B parts generally, while §5.1 says REQ "would land on the ID pin" and §7 step 4 instructs you
to "pull pin 4 low." If step 2's continuity check finds pin 4 shorted to GND — as it is here —
step 4 is not merely unnecessary, it is unperformable. The procedure should branch on step 2's
result rather than listing both.

### 10.4 Errors and soft spots found

1. **Stray tool-call markup at end of file.** Lines 515–517 contain `</content>` and `</invoke>`
   after the last source bullet. Delete.
2. **The "2 µs" sample delay derivation does not follow from its own citation.** §4.2 cites
   `scaleClockFirstReadDelay = F_CPU/4000000` and annotates it "= 2 µs at 16 MHz." At
   F_CPU = 16 MHz that expression evaluates to **4**, not 2. Depending on how the constant is
   consumed that is plausibly ~4 µs — which is notably close to the **4.75 µs** figure
   `PROTOCOL_RESEARCH.md` takes from Rysium, and would make the two sources agree. As written the
   document creates a conflict that may not exist. Worth re-reading the source line before pinning
   a sample delay into firmware.
3. **§4.3 range off by one.** 21-bit two's complement spans −1 048 576 … +1 048 575; the document
   writes "±1 048 575." Cosmetic, but it is a range check someone will code against.
4. **F1's 5 V warning is right for the wrong reason on this unit.** It warns that VBUS could exceed
   "the tool's 3 V rail" — but §11.3 established the connector exposes **no rail at all**, so on
   this unit a real USB port would land 5 V on a *signal* pin. Still dangerous, different mechanism.
   (This is the same conflation that investigation §2 makes — see §2.5.)
5. **§0's confidence outruns §2's.** Discussed in §10.2.
6. **§7's procedure is partly already executed.** Steps 2 and 3 are done; step 4 is unperformable
   (§10.3); step 5 has been run many times. A "what remains" pass over §7 against §11 would make it
   actionable rather than duplicative.
7. **Not an error, but worth noting:** §1's specification table reproduces resolution and accuracy
   from vendor sources and **does not** carry the 0.0005" repeatability figure that investigation §1
   lists. That is independent support for §6.3's suspicion that the 0.0005" number is a
   transcription error.

### 10.5 The one bench observation this research does not explain — and a lead it hands us

Nothing in any of F7/F10/F11–F13 predicts the project's central finding: **DATA button held +
edges on pin 2 or pin 3 → pin 1 asserts a long (≥25 ms) low.** None of the surveyed protocols has a
device-driven "data ready" line, and none has a button in the wire protocol at all.

But §5.3 contains a lead nobody has followed. Describing the reference Digimatic host circuit, it
notes: *"A second 10 kΩ biases the cable's 'data' pushbutton."* In that design the **data button is
electrically part of the port interface**, not a private input to the tool's own MCU. If iGaging
carried that idea over, the 35-065's DATA button may be wired — possibly via the `J10–J81` jumper
matrix — into the connector-pin network rather than being purely internal.

That reframes the observed behaviour: pin 1 may not be a protocol signal at all, but the
button/strobe line, which would explain why it is reading-independent (§1.1 caveats aside) and why
no clocking scheme has ever shifted data out of it. **Ringing the DATA button's contacts to Q1/Q2
and to connector pins 1/2/3 is a DMM-only test** and now joins §5.1 at the top of the queue.

### 10.6 Housekeeping

- **Two protocol-research files with near-identical names.** `PROTOCOL_RESEARCH.md` (2026-07-17) and
  `igaging_protcol_research.md` (2026-07-26) overlap heavily and **disagree** on sign encoding
  (one's vs two's), on DATA-line pull direction (pull-*down* vs pull-*up*/open-drain), and on
  whether a REQ line exists. The newer one is better on all three. Recommend either deleting
  `PROTOCOL_RESEARCH.md` or reducing it to a stub pointing at the new file; at minimum, banner it.
- **The filename typo (`protcol`) is deliberate** per the doc's own header note. Fine, but combined
  with the near-duplicate name it makes tab-completion a coin flip. Worth reconsidering.
- **Add it to the file table** in `BRINGUP_PLAN.md` §8, which lists every other document.

### 10.7 Net effect on this review

Nothing in §§1–4 is weakened. Three things get stronger:

- The damage question (§4) gains a named failure mode from F2 — though on analysis F2 describes
  hard-grounding a driven output, which is not what happened here, so §4 ends up *weaker*, not
  stronger. See the revision banner on §4.
- The "exhausted" claims (§3.1) get worse: two more never-varied stimulus parameters surface
  (20 % duty, §5.5a; 100 kΩ pull-ups, §5.7a) — both specified by the reference implementation, both
  never delivered by any test in this project.
- ~~The §11.13 Digimatic branch is largely closed by a measurement taken a month ago (§10.3).~~
  **Retracted — see the banner on §10.3.** Digimatic is open and arguably favoured; the pin count
  fits it and it resolves the §2.1 two-drivers contradiction.

And one thing gets cheaper: F8 lets `igaging_decode.py` pin `SIGN_ENCODING = "twos"` now, and F9
gives Phase C a two-way discrimination target instead of an open-ended fit.

---

## 11. Review of `igaging_dataconnect_hardware_findings.md` — hypothesis, not evidence

**What it is:** desk research into who manufactures the DataConnect kits, arguing from vendor
product photography that the 35-065 speaks Mitutoyo Digimatic. **Nothing in it was measured, it
never touched this micrometer, and it was written with no knowledge of this project** — it has not
seen `BENCH_LOG.md` and knows none of our pin roles, continuity results, or trigger conditions.
Weight it accordingly: it is a well-argued hypothesis that generates one good experiment. It is not
a finding, and it does not settle anything.

### 11.1 Its chain of inference, and where each link is load-bearing

1. iGaging = IPIC, a brander not a manufacturer → the "3rd party item" reply is literal. *Plausible
   and low-stakes.*
2. Both kits share the **same control box**; only the tool-end cable differs. *From product
   photos. Our own §11.13 made the same observation and was appropriately careful about it:*
   "we have NOT established the two control boxes are electrically identical — only that they look
   alike."
3. The box-end 2×5 connector is **the Mitutoyo Digimatic 10-pin standard** (1=GND, 2=DATA, 3=CLOCK,
   4=RDY, 5=REQ). *The standard and its pinout are well corroborated; that these photos show that
   connector is a visual identification.*
4. ⇒ the box is a generic Digimatic wedge ⇒ **if the adapter cable is passive**, the mic emits
   Digimatic. *The conditional is doing all the work, and the document concedes it — converter
   electronics in the connector hood is exactly how ASDQMS SmartCables work.*
5. **The button-count argument:** the box has one button (`DATA`). A Digimatic frame is
   self-describing, so one button suffices; a raw-count tool would need zero and units buttons.
   *This is the most interesting argument in the document — it reasons from a design constraint
   rather than from a photo detail. But it still reads a protocol off a photograph of a housing.*

### 11.2 The one thing worth acting on

**§6 — ohm out the adapter cable.** If the `100-700-USB-MC` is ever bought, buzz all five
micro-USB pins against all ten 2×5 pins *before* plugging anything in. Ten minutes, no power, no
risk, nothing opened. Five clean 1:1 connections means the cable is passive, which both confirms
Digimatic **and hands over the complete micro-USB pinout including which pin is REQ** — the single
biggest unknown in the project. Opens or diode drops mean active electronics and the inference
chain collapses. Either outcome is informative, which is what makes it a good experiment.

This is now **step 0 of the cable session** (§8, step 14), ahead of the in-line sniff.

Its §8 OEM leads (reverse-image the housing; look for the same box under Accusize / Dasqua /
Shahe / Insize; ask MicroRidge or ASDQMS whether their Digimatic wedges work with a 35-065) are
legitimate zero-cost research directions, though none produces a measurement.

### 11.3 What it does *not* change

- **It is not why Digimatic is back on the table.** That is §10.3's retraction, which rests on our
  own data: three signal pins plus two grounds is exactly Digimatic's minimum with VDD unneeded,
  and it resolves the §2.1 two-drivers contradiction. This document happens to agree; it is not the
  evidence.
- **It does not override §11.15/§11.16.** Our measured pin roles — one observed output, two inputs
  — remain the strongest counter-evidence to Digimatic, subject to the masking and weak-driver
  caveats already recorded (§3.4, §5.7a).
- **Its §7 correction of the three-button claim is worth noting** — the "zero/units/readout"
  description came from Alex Whittemore's blog about a cheaper, different micrometer and was
  carried into our own investigation §8 without verification. That much is a real sourcing catch,
  and it applies to our docs too.

### 11.4 Bonus: an open question from §1.1 is now closed by our own data

While checking this document's implications, the unexplained post-trigger structure on pin 1
(§1.1's "time-varying ±0.7 V envelope … never explained") was resolved against the captures:

| Capture | Injected clock | pin 1 toggle rate @ 0 V | ratio |
|---|---|---|---|
| `readingB` (clock on pin 3) | 8.40 kHz | 7.41 kHz | 0.883 |
| `readingA_clk2` (clock on pin 2) | 8.48 kHz | 7.45 kHz | 0.879 |

Near-identical ratios across two runs that used **different clock pins** means the activity tracks
the injected clock — it is crosstalk, undersampled (an ~8.4 kHz signal at 20 kSa/s aliases exactly
like this), **not** hidden device data. §1.1's conclusion is unaffected; that particular open thread
is closed.

One real observation survives: ~1.4 Vpp of crosstalk riding on a pin that is supposedly hard-driven
low by a saturated NPN is anomalous — a saturated transistor should swamp it. That is further
support for §5.7a's weak-driver concern and for §2.2's doubt about the "−0.7 V open-collector"
characterisation.
