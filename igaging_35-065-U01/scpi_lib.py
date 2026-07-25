"""Raw-socket SCPI clients for the bench instruments used to reverse-engineer the
iGaging 35-065-U01 micrometer data port.

Both instruments are Rigol LXI devices that expose a raw SCPI socket:
  - Scope: DHO814 oscilloscope  @ rigol-oscope.jasonantman.com:5555  (confirmed)
  - Awg:   DG902 Pro AWG        @ rigol-awg.jasonantman.com:5025      (confirmed 2026-07-17)

The base `SCPI` class is lifted from mxmoonfree_LS-20-6/scope_lib.py (proven against the
DHO814) and generalized so the same block/newline framing serves the AWG too.

Networking to the LAN instruments needs Bash `dangerouslyDisableSandbox`.
"""
import socket
import time

SCOPE_HOST = "rigol-oscope.jasonantman.com"
AWG_HOST = "rigol-awg.jasonantman.com"
PORT = 5555  # DHO814 raw-SCPI port (confirmed).
AWG_PORT = 5025  # DG902 Pro raw-SCPI port (confirmed 2026-07-17; it does NOT use 5555).


class SCPI:
    """Minimal raw-socket SCPI transport: line queries + IEEE 488.2 block reads."""

    def __init__(self, host, port=PORT, timeout=10):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def write(self, cmd):
        self.sock.sendall((cmd + "\n").encode())

    def _read_until_newline(self):
        buf = bytearray()
        while True:
            b = self.sock.recv(1)
            if not b or b == b"\n":
                break
            buf += b
        return buf

    def query(self, cmd):
        self.write(cmd)
        return self._read_until_newline().decode(errors="replace").strip()

    def read_block(self):
        """Read an IEEE 488.2 definite-length block: #NLLLL<bytes>\\n"""
        while True:
            c = self.sock.recv(1)
            if c == b"#":
                break
            if not c:
                raise IOError("EOF waiting for block header")
        ndig = int(self.sock.recv(1).decode())
        lenbytes = b""
        while len(lenbytes) < ndig:
            lenbytes += self.sock.recv(ndig - len(lenbytes))
        nbytes = int(lenbytes.decode())
        data = bytearray()
        while len(data) < nbytes:
            chunk = self.sock.recv(min(65536, nbytes - len(data)))
            if not chunk:
                raise IOError("EOF during block payload")
            data += chunk
        try:
            self.sock.recv(1)  # trailing newline
        except Exception:
            pass
        return bytes(data)

    def query_block(self, cmd):
        self.write(cmd)
        return self.read_block()


class Scope(SCPI):
    """Rigol DHO814 helpers: multi-channel single-shot capture + raw-memory readout."""

    def __init__(self, host=SCOPE_HOST, port=PORT, timeout=20):
        super().__init__(host, port, timeout)

    def setup_channel(self, ch, scale=0.5, offset=-1.5, coupling="DC"):
        self.write(f":CHANnel{ch}:DISPlay ON")
        self.write(f":CHANnel{ch}:COUPling {coupling}")
        self.write(f":CHANnel{ch}:SCALe {scale}")
        self.write(f":CHANnel{ch}:OFFSet {offset}")

    def disable_channel(self, ch):
        self.write(f":CHANnel{ch}:DISPlay OFF")

    def arm_single(self, trig_ch, level, slope="POSitive", mdepth=1_000_000, tb_scale=0.01,
                   sweep="NORMal"):
        # sweep=NORMal: only stops on a real trigger (use when the signal is guaranteed).
        # sweep=AUTO:   force-triggers if none arrives, so :SINGle always yields a window
        #               (use when the stimulus timing/alignment is uncertain — a captured
        #               window is then guaranteed and correctness is checked in analysis).
        self.write(":RUN")
        self.write(f":ACQuire:MDEPth {mdepth}")
        self.write(":TIMebase:MODE MAIN")  # DHO814: mode is :TIMebase:MODE, not :TIMebase:MAIN:MODE
        self.write(f":TIMebase:MAIN:SCALe {tb_scale}")
        self.write(":TIMebase:MAIN:OFFSet 0")
        self.write(":TRIGger:MODE EDGE")
        self.write(f":TRIGger:EDGE:SOURce CHANnel{trig_ch}")
        self.write(f":TRIGger:EDGE:SLOPe {slope}")
        self.write(f":TRIGger:EDGE:LEVel {level}")
        self.write(f":TRIGger:SWEep {sweep}")
        time.sleep(0.3)
        self.write(":SINGle")

    def measure_vavg(self, ch, settle=0.8, tb_scale=0.001, tries=10):
        """Read a channel's true DC average via :MEASure (AUTO sweep, no edge needed).

        Use this for flat DC lines (e.g. a supplied VDD rail) — an edge trigger can never
        fire on a level with no transitions, so arm_single()+read would hang/return stale.

        The DHO814 returns ~9.9E37 when a measurement isn't ready yet (no valid acquisition
        on screen). We RUN, let AUTO sweep fill a window, then poll until the value is real,
        raising if it never resolves — so a caller never mistakes the sentinel for a voltage.
        """
        self.write(":TIMebase:MODE MAIN")
        self.write(f":TIMebase:MAIN:SCALe {tb_scale}")
        self.write(":TRIGger:SWEep AUTO")
        self.write(":RUN")
        time.sleep(settle)
        v = float("inf")
        for _ in range(tries):
            v = float(self.query(f":MEASure:ITEM? VAVG,CHANnel{ch}"))
            if abs(v) < 1e30:  # real reading (sentinel is ~9.9E37)
                return v
            time.sleep(0.3)
        raise RuntimeError(f"VAVG on CH{ch} never resolved (last={v:.2e}); scope not acquiring?")

    def wait_stop(self, timeout=15):
        deadline = time.time() + timeout
        status = None
        while time.time() < deadline:
            status = self.query(":TRIGger:STATus?")
            if status == "STOP":
                return status
            time.sleep(0.1)
        return status

    def read_raw(self, ch, maxchunk=250000):
        """Return (preamble_str, raw_bytes) for a channel's full RAW acquisition memory."""
        self.write(f":WAVeform:SOURce CHANnel{ch}")
        self.write(":WAVeform:MODE RAW")
        self.write(":WAVeform:FORMat BYTE")
        pre = self.query(":WAVeform:PREamble?")
        points = int(float(pre.split(",")[2]))
        data = bytearray()
        start = 1
        while start <= points:
            stop = min(start + maxchunk - 1, points)
            self.write(f":WAVeform:STARt {start}")
            self.write(f":WAVeform:STOP {stop}")
            data += self.query_block(":WAVeform:DATA?")
            start = stop + 1
        return pre, bytes(data)

    def screenshot(self, path):
        data = self.query_block(":DISPlay:DATA? PNG")
        with open(path, "wb") as f:
            f.write(data)
        return len(data)


class Awg(SCPI):
    """Rigol DG902 Pro helpers.

    SAFETY: always drive the mic through a series resistor (~1-2.2 kOhm) and set the
    output to High-Z. If the AWG thinks it drives a 50 Ohm load but actually sees ~high
    impedance, the real pin voltage DOUBLES — a "1.5 V" setting becomes 3.0 V. High-Z
    makes the displayed/commanded amplitude equal the amplitude at the pin.
    """

    def __init__(self, host=AWG_HOST, port=AWG_PORT, timeout=10):
        super().__init__(host, port, timeout)

    def output(self, on, ch=1):
        self.write(f":OUTPut{ch} {'ON' if on else 'OFF'}")

    def set_highz(self, ch=1):
        # High-Z so commanded amplitude == amplitude at the pin (see class docstring).
        # DG902 Pro FIRMWARE TRAP (confirmed 2026-07-25): the spelled-out keyword
        # ":OUTPut:LOAD INFinity" is MIS-PARSED and silently sets the load to 1 ohm
        # (readback 1.0) — the worst case: the AWG then clamps commanded amplitude to
        # ~0.196 V and drives its full ~10 V EMF into a high-Z pin. The abbreviated form
        # ":OUTPut:LOAD INF" is the ONLY spelling that gives true High-Z (readback 9.9E37).
        # (":OUTPut:LOAD 10000" is the 10 kOhm max — near-High-Z but ~0.5% high, not exact;
        # numeric "9.9E37" also mis-parses to 1 ohm. Use INF.)
        self.write(f":OUTPut{ch}:LOAD INF")
        rb = self.query(f":OUTPut{ch}:LOAD?")
        if "E+3" not in rb and "E37" not in rb:  # expect ~9.9E+37 for High-Z
            raise RuntimeError(f"CH{ch} High-Z NOT set (LOAD readback {rb!r}); refusing to drive.")

    def dc(self, volts, ch=2):
        """Configure (but do NOT enable) channel `ch` as a High-Z DC source at `volts`.

        Used to supply VDD into connector pin 1. Verify the actual level on the scope before
        trusting it (start low): commanded == delivered only in High-Z mode.
        """
        self.set_highz(ch)
        self.write(f":SOURce{ch}:APPLy:DC 1,1,{volts}")

    def square(self, freq, low=0.0, high=1.5, duty=50, ch=1):
        """Configure (but do NOT enable) a 0->high square-wave clock.

        Uses explicit LOW/HIGH levels so a 0 V-referenced clock is unambiguous.
        """
        self.set_highz(ch)
        self.write(f":SOURce{ch}:FUNCtion SQUare")
        self.write(f":SOURce{ch}:FREQuency {freq}")
        # Some firmwares require amplitude/offset before LOW/HIGH will take; set both ways.
        self.write(f":SOURce{ch}:VOLTage:LOW {low}")
        self.write(f":SOURce{ch}:VOLTage:HIGH {high}")
        self.write(f":SOURce{ch}:FUNCtion:SQUare:DCYCle {duty}")

    def set_high_level(self, high, low=0.0, ch=1):
        """Change amplitude mid-ramp without reconfiguring the whole waveform."""
        self.write(f":SOURce{ch}:VOLTage:LOW {low}")
        self.write(f":SOURce{ch}:VOLTage:HIGH {high}")


if __name__ == "__main__":
    import sys

    which = sys.argv[1] if len(sys.argv) > 1 else "scope"
    if which == "awg":
        a = Awg()
        print("AWG IDN:", a.query("*IDN?"))
        a.close()
    else:
        s = Scope()
        print("SCOPE IDN:", s.query("*IDN?"))
        s.close()
