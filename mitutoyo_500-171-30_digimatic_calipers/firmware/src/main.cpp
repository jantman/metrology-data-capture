/*
 * Mitutoyo 500-171-30 Digimatic caliper (via 959149 SPC cable) -> USB HID keyboard (ESP32-S3)
 * ============================================================================================
 *
 * Press the DATA button ON THE CALIPER'S OWN CABLE and the reading is "typed" into whatever
 * field has focus on the host -- no host-side software. A 2-circuit DIP switch selects the key
 * sent AFTER the number (Enter / Tab / nothing).
 *
 * PASSIVE LISTENER BY DESIGN. This firmware never drives a single wire into the caliper. The
 * 959149's built-in DATA switch already grounds REQ, which is what makes the tool emit a frame;
 * we only watch CK and DATA go by. Consequences worth keeping in mind if you extend this:
 *   - REQ is not connected to the MCU at all. There is no "read now" command, and no way for a
 *     firmware bug to inject current into a 1.55 V instrument.
 *   - Readings are event-driven, not polled: nothing arrives until the button is pressed, so
 *     unlike the LS-20 firmware there is no free-running stream and no staleness check needed.
 *     Whatever we decode is by definition freshly measured.
 *
 * Protocol (13 nibbles = 52 bits, nibble-wise, LSB of each nibble first):
 *   nibbles 1-4  : 0xF preamble        nibble 5   : sign (0 = +, nonzero = -)
 *   nibbles 6-11 : six BCD digits, MSD first
 *   nibble 12    : decimal-point position (number of decimals)
 *   nibble 13    : units (0 = mm, 1 = inch)
 * Mirrors ../digimatic_decode.py; keep the two in step.
 *
 * WIRE POLARITY IS AUTO-DETECTED, not assumed. CK/DATA are open-collector, so whether a logic 1
 * is a high or a low on the pin depends on the front end. The preamble is a constant 0xFFFF, so
 * the firmware simply tries both polarities and keeps whichever one produces it. That also makes
 * a misaligned 52-bit window self-rejecting: no preamble, no keystroke.
 *
 * ---- Wiring (all referenced to Digimatic pin 1 = GND) ----
 *   Digimatic pin 3 (CK)   -> GPIO16   via the front end (see ../README.md)
 *   Digimatic pin 2 (DATA) -> GPIO5    via the front end
 *   Digimatic pin 4 (RDY)  -> GPIO6    optional, diagnostic only (may be absent on calipers)
 *   Digimatic pin 5 (REQ)  -> NOT CONNECTED  -- deliberately; the cable's switch owns it
 *   Digimatic pin 1 (GND)  -> ESP32 GND
 *   DIP sw 1 -> GPIO7  to GND      DIP sw 2 -> GPIO15 to GND   (internal pull-ups, closed = low)
 *
 * GPIO choices match the LS-20 build: clear of the S3 strapping pins (0,3,45,46), the native-USB
 * pins (19,20) and the flash/PSRAM pins (26-37), all on one header side.
 */
#include <Arduino.h>
#include "USB.h"
#include "USBHIDKeyboard.h"

// ----------------------------- Pin map -----------------------------
static const int PIN_CK    = 16;   // Digimatic pin 3
static const int PIN_DATA  = 5;    // Digimatic pin 2
static const int PIN_RDY   = 6;    // Digimatic pin 4 (diagnostic only)
static const int PIN_DIP0  = 7;
static const int PIN_DIP1  = 15;

// -------------------------- Protocol params ------------------------
static const uint8_t  FRAME_BITS = 52;
static const uint64_t FRAME_MASK = (1ULL << FRAME_BITS) - 1;

// Resync threshold. Must sit above the largest intra-frame gap and below the shortest gap
// between two button presses. Published implementations put a whole frame at ~34 ms (~650 us
// per bit); spc_capture.py prints the measured intra-frame gaps -- if any approaches this,
// raise it.
static const uint32_t FRAME_GAP_US = 5000;

// Sample DATA on the clock edge where the tool asserts CK (falling, for an idle-high
// open-collector line). Flip to 1 if the bench capture shows data valid on the other edge.
#define SAMPLE_ON_RISING 0

// One keystroke per button press: after typing, wait for the clock to go quiet before another
// frame is eligible. If the tool streams while the button is held, this stops a value storm.
// Set STREAM_MODE to 1 to type every frame instead (useful for logging).
#define STREAM_MODE 0
static const uint32_t QUIET_US = 250000;

USBHIDKeyboard Keyboard;

// --------------------- ISR <-> loop shared state -------------------
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
static volatile uint64_t isrAccum    = 0;
static volatile uint8_t  isrBits     = 0;
static volatile uint32_t isrLastEdge = 0;   // micros() of the previous clock edge
static volatile uint64_t latchedFrame = 0;
static volatile bool     frameValid   = false;

// Clock-edge ISR: a long gap resyncs to a frame boundary; 52 bits latches a frame. Bit i of the
// accumulator is the i'th bit off the wire, so nibble n is simply (accum >> 4n) & 0xF.
void IRAM_ATTR clockIsr() {
  uint32_t now = micros();
  uint32_t gap = now - isrLastEdge;
  isrLastEdge  = now;

  portENTER_CRITICAL_ISR(&mux);
  if (gap > FRAME_GAP_US) {          // start of a new transmission
    isrAccum = 0;
    isrBits  = 0;
  }
  if (isrBits < FRAME_BITS) {
    isrAccum |= ((uint64_t)(digitalRead(PIN_DATA) ? 1 : 0)) << isrBits;
    isrBits++;
    if (isrBits == FRAME_BITS) {     // complete -> hand it to the loop, keep listening
      latchedFrame = isrAccum;
      frameValid   = true;
      isrAccum = 0;
      isrBits  = 0;
    }
  }
  portEXIT_CRITICAL_ISR(&mux);
}

// --------------------------- Decode/format -------------------------
struct Reading {
  bool     ok;
  bool     inverted;      // wire polarity that produced the preamble
  char     text[16];      // display-ready, built from digits+dp (no float math anywhere)
  char     unit[3];
  uint64_t frame;         // logic-true frame (already de-inverted)
};

static inline uint8_t nib(uint64_t f, int n) { return (uint8_t)((f >> (4 * n)) & 0xF); }

static bool hasPreamble(uint64_t f) {
  return nib(f, 0) == 0xF && nib(f, 1) == 0xF && nib(f, 2) == 0xF && nib(f, 3) == 0xF;
}

// Decode a 52-bit wire frame. Returns ok=false for anything that fails a structural check --
// which is the whole defence against typing garbage, since we type unattended on arrival.
static Reading decodeFrame(uint64_t wire) {
  Reading r = {};
  uint64_t f = wire & FRAME_MASK;
  if (hasPreamble(f)) {
    r.inverted = false;
  } else if (hasPreamble((~f) & FRAME_MASK)) {
    f = (~f) & FRAME_MASK;
    r.inverted = true;
  } else {
    return r;                                   // no preamble in either polarity
  }
  r.frame = f;

  uint8_t sign = nib(f, 4);
  uint8_t dp   = nib(f, 11);
  uint8_t unit = nib(f, 12);
  if (dp > 6 || unit > 1) return r;

  char digits[7];
  for (int i = 0; i < 6; i++) {
    uint8_t d = nib(f, 5 + i);
    if (d > 9) return r;                        // not BCD -> not a reading
    digits[i] = (char)('0' + d);
  }
  digits[6] = '\0';

  bool nonzero = false;
  for (int i = 0; i < 6; i++) if (digits[i] != '0') nonzero = true;
  bool negative = (sign != 0) && nonzero;       // never emit "-0.00"

  // Split the six digits at the decimal point, strip leading zeros, keep trailing ones so the
  // string matches the LCD digit-for-digit.
  char ipart[8], fpart[8];
  int ilen = 6 - dp;
  memcpy(ipart, digits, ilen); ipart[ilen] = '\0';
  strcpy(fpart, digits + ilen);
  const char *ip = ipart;
  while (*ip == '0' && *(ip + 1) != '\0') ip++;
  if (ilen == 0) ip = "0";

  if (dp) snprintf(r.text, sizeof(r.text), "%s%s.%s", negative ? "-" : "", ip, fpart);
  else    snprintf(r.text, sizeof(r.text), "%s%s",    negative ? "-" : "", ip);
  strcpy(r.unit, unit == 1 ? "in" : "mm");
  r.ok = true;
  return r;
}

// Terminator select from the 2-circuit DIP (closed switch pulls the pin LOW):
//   0 (both open) = none   1 = Enter   2 = Tab   3 (both closed) = none
static int terminatorCode() {
  int b0 = (digitalRead(PIN_DIP0) == LOW) ? 1 : 0;
  int b1 = (digitalRead(PIN_DIP1) == LOW) ? 1 : 0;
  int code = b0 | (b1 << 1);
  return (code == 3) ? 0 : code;
}

// ---------------------------- Self-test ----------------------------
// Build a wire frame from a known reading, exactly as ../digimatic_decode.py's encode_frame()
// does, so the bit arithmetic can be checked over serial with no caliper attached.
static uint64_t buildFrame(const char *digits, uint8_t dp, bool inch, bool negative,
                           uint8_t signValue, bool invert) {
  uint8_t nibs[13] = {0xF, 0xF, 0xF, 0xF, (uint8_t)(negative ? signValue : 0)};
  for (int i = 0; i < 6; i++) nibs[5 + i] = (uint8_t)(digits[i] - '0');
  nibs[11] = dp;
  nibs[12] = inch ? 1 : 0;
  uint64_t f = 0;
  for (int n = 0; n < 13; n++) f |= ((uint64_t)nibs[n]) << (4 * n);
  return invert ? ((~f) & FRAME_MASK) : f;
}

static void selfTest() {
  struct { const char *digits; uint8_t dp; bool inch; bool neg; const char *expect; } cases[] = {
    {"000000", 2, false, false, "0.00"},
    {"000123", 2, false, false, "1.23"},
    {"001000", 2, false, false, "10.00"},
    {"015000", 2, false, false, "150.00"},
    {"002000", 2, false, true,  "-20.00"},
    {"009840", 4, true,  false, "0.9840"},
    {"059055", 4, true,  true,  "-5.9055"},
  };
  Serial.println("[selftest] synthesized frames, both wire polarities:");
  bool ok = true;
  for (auto &c : cases) {
    for (int inv = 0; inv < 2; inv++) {
      Reading r = decodeFrame(buildFrame(c.digits, c.dp, c.inch, c.neg, 8, inv));
      bool pass = r.ok && strcmp(r.text, c.expect) == 0 && r.inverted == (bool)inv;
      ok &= pass;
      Serial.printf("  %s %s %-8s %s (expect %s)\n", pass ? "OK  " : "FAIL",
                    inv ? "inv" : "std", r.ok ? r.text : "<reject>", r.unit, c.expect);
    }
  }
  // The sign nibble is reported as either 8 or 1 by different sources; both must read negative.
  Reading r1 = decodeFrame(buildFrame("000500", 2, false, true, 1, false));
  Reading r8 = decodeFrame(buildFrame("000500", 2, false, true, 8, false));
  bool signOk = r1.ok && r8.ok && !strcmp(r1.text, "-5.00") && !strcmp(r8.text, "-5.00");
  ok &= signOk;
  Serial.printf("  %s sign nibble 1 and 8 both negative\n", signOk ? "OK  " : "FAIL");
  // Garbage must be rejected in both polarities, or we would type it.
  bool rej = !decodeFrame(0xAAAAAAAAAAAAAULL).ok;
  ok &= rej;
  Serial.printf("  %s garbage frame rejected\n", rej ? "OK  " : "FAIL");
  Serial.println(ok ? "[selftest] ALL PASS" : "[selftest] FAILURES PRESENT");
}

// ------------------------------ Arduino ----------------------------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\nMitutoyo 500-171-30 Digimatic -> USB HID keyboard (passive listener)");

  pinMode(PIN_CK,   INPUT);            // high-Z: the front end supplies the pull-ups
  pinMode(PIN_DATA, INPUT);
  pinMode(PIN_RDY,  INPUT);
  pinMode(PIN_DIP0, INPUT_PULLUP);
  pinMode(PIN_DIP1, INPUT_PULLUP);

  selfTest();

#if SAMPLE_ON_RISING
  attachInterrupt(digitalPinToInterrupt(PIN_CK), clockIsr, RISING);
#else
  attachInterrupt(digitalPinToInterrupt(PIN_CK), clockIsr, FALLING);
#endif

  Keyboard.begin();
  USB.begin();
  Serial.println("[setup] ready -- press the DATA button on the caliper cable");
}

void loop() {
  static bool suppressed = false;      // one keystroke per press (see STREAM_MODE)

  uint64_t frame = 0;
  bool have = false;
  portENTER_CRITICAL(&mux);
  if (frameValid) { frame = latchedFrame; frameValid = false; have = true; }
  portEXIT_CRITICAL(&mux);

  if (have) {
    Reading r = decodeFrame(frame);
    if (!r.ok) {
      Serial.printf("[rx] rejected frame 0x%013llX (no preamble / not BCD)\n",
                    (unsigned long long)frame);
    } else if (suppressed) {
      Serial.printf("[rx] %s %s (suppressed -- release the DATA button)\n", r.text, r.unit);
    } else {
      Keyboard.print(r.text);
      int term = terminatorCode();
      if (term == 1)      Keyboard.write('\n');
      else if (term == 2) Keyboard.write('\t');
      Serial.printf("[type] %s %s  (frame=0x%013llX, %s, term=%d)\n", r.text, r.unit,
                    (unsigned long long)r.frame, r.inverted ? "inverted" : "as-wired", term);
#if !STREAM_MODE
      suppressed = true;
#endif
    }
  }

  if (suppressed) {                    // re-arm once the line has been quiet
    portENTER_CRITICAL(&mux);
    uint32_t since = micros() - isrLastEdge;
    portEXIT_CRITICAL(&mux);
    if (since > QUIET_US) suppressed = false;
  }
}
