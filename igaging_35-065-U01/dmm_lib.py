"""HTTP client for the OWON XDM1041 bench multimeter.

The meter exposes an unauthenticated JSON API on the LAN (see http://HOST:8080/api,
OpenAPI at /openapi.json):
  GET  /api/state                 -> {function, rate, auto_range, range}
  GET  /api/identify              -> identity string
  GET  /api/measurement           -> {timestamp, function, value, unit}
  GET  /api/measurement/smoothed  -> rolling mean/min/max over `seconds`
  POST /api/function {function}   -> set function (VOLT_DC, DIODE, RESISTANCE, ...)
  POST /api/rate {rate}           -> SLOW | MEDIUM | FAST
  POST /api/auto-range {enabled}

Used for the closed-case port health checks on the iGaging data port (review.md §4.3):
diode-testing connector pins 1/2/3 against GND through the Micro-USB breakout.

Networking to the LAN host needs Bash `dangerouslyDisableSandbox`.
"""
import json
import time
import urllib.request

DMM_URL = "http://owon-dmm.jasonantman.com:8080"

# The API is asymmetric on purpose: /api/function takes a MODE name, while /api/measurement
# reports the measured QUANTITY, which is not always the same string.
#     set RESISTANCE -> reads back as "RES"      set VOLT_DC -> reads back as "VOLT"
# A naive prefix check ("RESISTANCE"[:4] == "RESI") fails against "RES", so map explicitly and
# fall back to a BIDIRECTIONAL prefix test for anything unmapped, rather than hard-failing on a
# mode nobody has exercised yet.
MEASURED_AS = {
    "VOLT_DC": "VOLT", "VOLT_AC": "VOLT",
    "CURR_DC": "CURR", "CURR_AC": "CURR",
    "RESISTANCE": "RES",
    "CAPACITANCE": "CAP",
    "CONTINUITY": "CONT",
    "TEMPERATURE": "TEMP",
    "DIODE": "DIODE", "FREQ": "FREQ", "PERIOD": "PERIOD",
}


def function_matches(reported, expected):
    """True if the meter's reported quantity corresponds to the requested mode."""
    rep, exp = reported.upper(), expected.upper()
    mapped = MEASURED_AS.get(exp)
    if mapped:
        return rep == mapped.upper()
    return rep.startswith(exp) or exp.startswith(rep)


class DMM:
    def __init__(self, base=DMM_URL, timeout=10):
        self.base = base.rstrip("/")
        self.timeout = timeout

    def _get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=self.timeout) as r:
            return json.load(r)

    def _post(self, path, payload):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def identify(self):
        return self._get("/api/identify")["identity"]

    def state(self):
        return self._get("/api/state")

    def measurement(self):
        return self._get("/api/measurement")

    def smoothed(self, seconds=3.0):
        return self._get(f"/api/measurement/smoothed?seconds={seconds}")

    def set_function(self, function):
        """function: VOLT_DC | VOLT_AC | CURR_DC | RESISTANCE | DIODE | CONTINUITY | ..."""
        return self._post("/api/function", {"function": function})

    def set_rate(self, rate):
        return self._post("/api/rate", {"rate": rate})

    def read_settled(self, expect_function=None, settle_s=1.5, tries=12, tol=0.002):
        """Read once the value stops moving — returns (value, unit).

        The meter free-runs, so a read taken right after the probes touch can catch a
        mid-transition sample. This polls until two consecutive readings agree within
        `tol` (relative or absolute, whichever is looser), or gives up and returns the
        last reading. `expect_function` guards against reading in the wrong mode.
        """
        time.sleep(settle_s)
        prev = None
        val = unit = None
        for _ in range(tries):
            m = self.measurement()
            val, unit = m["value"], m["unit"]
            if expect_function and not function_matches(m["function"], expect_function):
                raise RuntimeError(
                    f"meter is in {m['function']}, expected {expect_function} — set_function() first")
            if prev is not None and abs(val - prev) <= max(tol, abs(val) * tol):
                return val, unit
            prev = val
            time.sleep(0.4)
        return val, unit


if __name__ == "__main__":
    d = DMM()
    print("IDENT:", d.identify())
    print("STATE:", json.dumps(d.state()))
    print("READ :", json.dumps(d.measurement()))
