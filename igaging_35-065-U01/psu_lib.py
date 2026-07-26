"""HTTP client for the B&K Precision 169x bench supply (used as the pull-up rail).

The supply exposes an unauthenticated JSON API on the LAN (see http://HOST:8088/api):
  GET  /api/state            -> full snapshot (voltage/current/mode/output_on/...)
  GET  /api/identify         -> identity string
  POST /api/voltage {voltage}    set voltage setpoint
  POST /api/current {current}    set current-limit setpoint
  POST /api/output  {on}         enable/disable output
  POST /api/ovp     {voltage}    over-voltage protection threshold

Used to supply the +3 V open-collector pull-up rail for the iGaging data-port tests.
Networking to the LAN host needs Bash `dangerouslyDisableSandbox`.
"""
import json
import urllib.request

PSU_URL = "http://owon-dmm.jasonantman.com:8088"


class PSU:
    def __init__(self, base=PSU_URL, timeout=10):
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

    def state(self):
        return self._get("/api/state")

    def identify(self):
        return self._get("/api/identify")["identity"]

    def set_voltage(self, v):
        return self._post("/api/voltage", {"voltage": float(v)})

    def set_current(self, a):
        return self._post("/api/current", {"current": float(a)})

    def set_ovp(self, v):
        return self._post("/api/ovp", {"voltage": float(v)})

    def output(self, on):
        return self._post("/api/output", {"on": bool(on)})

    def bring_up(self, volts, ilim, ovp=None, settle_s=0.6):
        """Safely bring the rail up: limit current FIRST, then voltage, then OVP, then enable.

        Verifies afterward and raises if the supply came up in CC (current-limited) with the
        voltage collapsed -- that means a short / heavy load on the rail (check wiring before
        trusting any result). Returns the fresh state dict.
        """
        import time
        self.output(False)
        self.set_current(ilim)          # cap current before any voltage is live
        self.set_voltage(volts)
        if ovp is not None:
            self.set_ovp(ovp)
        self.output(True)
        time.sleep(settle_s)
        st = self.state()
        v, mode = st.get("voltage"), st.get("mode")
        print(f"[PSU] {self.identify()}")
        print(f"[PSU] set {volts:.2f} V / {ilim*1000:.0f} mA limit -> reads {v:.3f} V, "
              f"{st.get('current',0)*1000:.1f} mA, mode {mode}, output {st.get('output_on')}")
        if mode == "CC" or (v is not None and v < volts * 0.8):
            raise RuntimeError(
                f"PSU came up CURRENT-LIMITED ({v:.2f} V, {st.get('current',0)*1000:.0f} mA, "
                f"mode {mode}) -> a short / heavy load on the {volts:.1f} V rail. Check wiring "
                f"before trusting results.")
        return st

    def off(self):
        try:
            return self.output(False)
        except Exception:
            pass


if __name__ == "__main__":
    p = PSU()
    print("IDENT:", p.identify())
    print("STATE:", json.dumps(p.state(), indent=2))
