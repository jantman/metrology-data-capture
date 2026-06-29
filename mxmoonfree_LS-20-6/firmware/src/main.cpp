/*
 * Mxmoonfree LS-20-6 digital caliper  ->  USB HID keyboard (ESP32-S3)
 * =====================================================================
 *
 * Press the button: the most-recent caliper reading is "typed" into whatever
 * field has focus on the host computer (text box, spreadsheet cell, ...), so it
 * can be captured without any host-side software. A 2-circuit DIP switch selects
 * the key sent AFTER the number (Enter / Tab / nothing).
 *
 * Protocol (fully reverse-engineered & LCD-verified 2026-06-21; see
 * ../caliper_decode.py and ../reverse-engineering/claude_desktop_initial_investigation.md):
 *   - Proprietary ~3 V synchronous serial on a Micro-USB jack (NOT USB).
 *   - 24-bit frame, LSB first, ~274 us/bit, a new frame every ~107 ms (continuous).
 *   - Clock idles HIGH and pulses LOW; DATA is valid on the clock RISING edge.
 *   - bits 0..19 = unsigned magnitude   bit 20 = sign(1=neg)   bit 23 = unit(1=inch)
 *   - mm = magnitude/100 (0.01 mm)      inch = magnitude/2000 (0.0005 in)
 *
 * CAVEAT: the caliper's pre-/pre+ preset buttons offset the LCD display ONLY.
 * The data port always transmits the raw measured value, so the typed value will
 * not match the display when a preset is active. (Confirmed in RE blind test F.)
 *
 * ---- Wiring (everything referenced to caliper Pin 5 = battery NEGATIVE) ----
 *   Caliper Pin 2 (CLOCK, idle high) -> GPIO16 (interrupt input)
 *   Caliper Pin 3 (DATA)             -> GPIO5  (input)
 *   Caliper Pin 5 (GND)              -> ESP32 GND
 *   Caliper Pin 1 (VBUS, ~3 V body)  -> LEAVE UNCONNECTED  (body is battery +!)
 *   Caliper Pin 4 (ID,  tied to body)-> LEAVE UNCONNECTED
 *   Button   -> GPIO6,  other side to GND        (internal pull-up; active low)
 *   DIP sw 1 -> GPIO7,  other side to GND        (internal pull-up; closed = low)
 *   DIP sw 2 -> GPIO15, other side to GND        (internal pull-up; closed = low)
 *
 * No level shifter, inverter, or pull-downs into the caliper: logic is the full
 * ~3 V rail and reads directly on the 3.3 V GPIOs. A 1-10 kOhm series resistor in
 * each of the clock/data lines is harmless insurance (optional).
 *
 * All four signal pins (16,5,6,7,15) sit on the same header side for easy
 * breakout wiring. GPIO choices avoid the S3 strapping pins (0,3,45,46), the
 * native-USB pins (19,20), and the SPI-flash/PSRAM pins (26-37) -- safe on every
 * S3 module variant.
 */
#include <Arduino.h>
#include "USB.h"
#include "USBHIDKeyboard.h"

// ----------------------------- Pin map -----------------------------
static const int PIN_CLOCK  = 16;   // caliper Pin 2
static const int PIN_DATA   = 5;    // caliper Pin 3
static const int PIN_BUTTON = 6;    // momentary, to GND
static const int PIN_DIP0   = 7;    // terminator-select bit 0, to GND
static const int PIN_DIP1   = 15;   // terminator-select bit 1, to GND

// -------------------------- Protocol params ------------------------
static const uint32_t FRAME_GAP_US = 2000;  // > max intra-frame gap (~0.55 ms),
                                            // << inter-frame gap (~100 ms)
static const uint8_t  FRAME_BITS   = 24;
static const uint32_t DEBOUNCE_MS  = 25;

// Frames arrive continuously at ~9 Hz (every ~107 ms). If the newest latched frame
// is older than this, the caliper is unplugged/off (or never connected) -> don't
// type. Also rejects the sticky-garbage failure mode where a one-off noise burst on
// the floating clock pin latched a frame that then "typed forever".
static const uint32_t SIGNAL_TIMEOUT_MS = 300;   // ~3 frame periods of tolerance

// Plausibility bound on the 20-bit magnitude. The LS-20-6 tops out at 500.00 mm =
// 50000 counts (inch mode is smaller); a floating DATA pin reads all-high -> magnitude
// 0xFFFFF (1048575), which this rejects. Bits 21/22 are unused and must be 0.
static const uint32_t MAX_MAGNITUDE = 60000;     // 50000 + headroom

USBHIDKeyboard Keyboard;

// --------------------- ISR <-> loop shared state -------------------
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
static volatile uint32_t isrAccum    = 0;   // bits accumulated for the in-progress frame
static volatile uint8_t  isrBits     = 0;   // count of bits accumulated
static volatile uint32_t isrLastEdge = 0;   // micros() of the previous rising edge
static volatile uint32_t latchedFrame = 0;  // last COMPLETE 24-bit frame
static volatile bool     frameValid   = false;
static volatile uint32_t latchedAtMs  = 0;  // millis() when latchedFrame was captured

// A real reading: unused bits 21/22 clear and magnitude within the caliper's range.
// Filters out the all-high garbage a floating clock/data pin produces when no caliper
// is attached. Pure bit math, safe to inline into the IRAM ISR.
static inline bool frameIsPlausible(uint32_t frame) {
  if (frame & (0x3u << 21)) return false;          // bits 21,22 must be 0
  return (frame & 0xFFFFFu) <= MAX_MAGNITUDE;      // magnitude in range
}

// Rising-edge ISR: a long gap since the previous edge marks a frame boundary, at
// which point the bits gathered so far were a complete frame; then this edge is
// bit 0 of the next frame. Data is sampled here because it is valid at the edge.
void IRAM_ATTR clockIsr() {
  uint32_t now = micros();
  uint32_t gap = now - isrLastEdge;
  isrLastEdge  = now;

  portENTER_CRITICAL_ISR(&mux);
  if (gap > FRAME_GAP_US) {
    if (isrBits >= FRAME_BITS && frameIsPlausible(isrAccum)) {  // finished + real -> latch
      latchedFrame = isrAccum;
      frameValid   = true;
      latchedAtMs  = millis();
    }
    isrAccum = 0;
    isrBits  = 0;
  }
  if (isrBits < 32) {                  // shift in this bit, LSB first
    isrAccum |= ((uint32_t)(digitalRead(PIN_DATA) ? 1u : 0u) << isrBits);
  }
  isrBits++;
  portEXIT_CRITICAL_ISR(&mux);
}

// --------------------------- Decode/format -------------------------
// Build the displayed-resolution string for a 24-bit frame using integer math
// (exact; no float rounding). mm -> 2 decimals, inch -> 4 decimals (each LSB =
// 0.0005 in = 5 ten-thousandths).
static String formatReading(uint32_t frame) {
  uint32_t magnitude = frame & 0xFFFFFu;          // bits 0..19
  bool     negative  = (frame >> 20) & 0x1u;      // bit 20
  bool     isInch    = (frame >> 23) & 0x1u;      // bit 23
  const char *sign   = (negative && magnitude) ? "-" : "";

  char buf[24];
  if (isInch) {
    uint32_t ip = magnitude / 2000;
    uint32_t fp = (magnitude % 2000) * 5;         // -> 4-decimal fraction, exact
    snprintf(buf, sizeof(buf), "%s%lu.%04lu", sign, (unsigned long)ip, (unsigned long)fp);
  } else {
    uint32_t ip = magnitude / 100;
    uint32_t fp = magnitude % 100;
    snprintf(buf, sizeof(buf), "%s%lu.%02lu", sign, (unsigned long)ip, (unsigned long)fp);
  }
  return String(buf);
}

// Terminator select from the 2-circuit DIP (closed switch pulls the pin LOW):
//   0 (both open) = none   1 = Enter   2 = Tab   3 (both closed) = none
static int terminatorCode() {
  int b0 = (digitalRead(PIN_DIP0) == LOW) ? 1 : 0;
  int b1 = (digitalRead(PIN_DIP1) == LOW) ? 1 : 0;
  int code = b0 | (b1 << 1);
  return (code == 3) ? 0 : code;
}

// ------------------------------ Action -----------------------------
static void typeReading() {
  uint32_t frame;
  bool valid;
  uint32_t ageMs;
  portENTER_CRITICAL(&mux);
  frame = latchedFrame;
  valid = frameValid;
  ageMs = millis() - latchedAtMs;
  portEXIT_CRITICAL(&mux);

  if (!valid) {
    Serial.println("[type] no caliper frame yet -- is the caliper connected/on?");
    return;
  }
  if (ageMs > SIGNAL_TIMEOUT_MS) {                 // stream stopped -> signal lost
    Serial.printf("[type] caliper signal stale (%lu ms old) -- not typing\n",
                  (unsigned long)ageMs);
    return;
  }
  String s = formatReading(frame);
  Keyboard.print(s);
  int term = terminatorCode();
  if (term == 1)      Keyboard.write('\n');   // Enter
  else if (term == 2) Keyboard.write('\t');   // Tab
  Serial.printf("[type] %s  (frame=0x%06lX, term=%d)\n", s.c_str(),
                (unsigned long)frame, term);
}

// ---------------------------- Self-test ----------------------------
// Decode the 5 LCD-verified ground-truth vectors at boot (LSB-first bitstrings,
// straight from caliper_decode.py) so the bit math can be confirmed over the
// debug serial port before any caliper is attached.
static uint32_t wordFromLSBString(const char *s) {
  uint32_t w = 0;
  for (int i = 0; s[i]; i++)
    if (s[i] == '1') w |= (1u << i);
  return w;
}

static void selfTest() {
  struct { const char *bits; const char *expect; } cases[] = {
    {"000000000000000000000000", "0.00"},
    {"000101111100000000000000", "10.00"},
    {"000010001110010000000000", "100.00"},
    {"000010111110000000001000", "-20.00"},
    {"000011011110000000000001", "0.9840"},
  };
  Serial.println("[selftest] decoding ground-truth vectors:");
  bool ok = true;
  for (auto &c : cases) {
    String got = formatReading(wordFromLSBString(c.bits));
    bool pass = (got == c.expect);
    ok &= pass;
    Serial.printf("  %s  %s -> %-8s (expect %s)\n", pass ? "OK  " : "FAIL",
                  c.bits, got.c_str(), c.expect);
  }
  Serial.println(ok ? "[selftest] ALL PASS" : "[selftest] FAILURES PRESENT");
}

// ------------------------------ Arduino ----------------------------
void setup() {
  Serial.begin(115200);                 // UART0 -> CP210x "UART" jack (debug)
  delay(200);
  Serial.println("\nLS-20 caliper -> USB HID keyboard");

  pinMode(PIN_CLOCK,  INPUT);           // high-Z: never drive the caliper lines
  pinMode(PIN_DATA,   INPUT);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(PIN_DIP0,   INPUT_PULLUP);
  pinMode(PIN_DIP1,   INPUT_PULLUP);

  selfTest();

  attachInterrupt(digitalPinToInterrupt(PIN_CLOCK), clockIsr, RISING);

  Keyboard.begin();
  USB.begin();                          // enumerate HID on the native-USB jack
  Serial.println("[setup] ready -- press the button to type the current reading");
}

void loop() {
  // Debounced HIGH->LOW (press) detector; fires typeReading() once per press.
  static int      stable    = HIGH;
  static int      lastRaw   = HIGH;
  static uint32_t lastEdge  = 0;

  int raw = digitalRead(PIN_BUTTON);
  if (raw != lastRaw) {
    lastRaw  = raw;
    lastEdge = millis();
  }
  if (millis() - lastEdge > DEBOUNCE_MS && raw != stable) {
    stable = raw;
    if (stable == LOW) typeReading();   // active-low press
  }
}
