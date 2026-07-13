"""Raw-socket SCPI clients for the bench instruments used to reverse-engineer the
iGaging 35-065-U01 micrometer data port.

Both instruments are Rigol LXI devices that expose a raw SCPI socket:
  - Scope: DHO814 oscilloscope  @ rigol-oscope.jasonantman.com:5555  (confirmed)
  - Awg:   DG902 Pro AWG        @ rigol-awg.jasonantman.com:5555      (port TO VERIFY)

The base `SCPI` class is lifted from mxmoonfree_LS-20-6/scope_lib.py (proven against the
DHO814) and generalized so the same block/newline framing serves the AWG too.

Networking to the LAN instruments needs Bash `dangerouslyDisableSandbox`.
"""
import socket
import time

SCOPE_HOST = "rigol-oscope.jasonantman.com"
AWG_HOST = "rigol-awg.jasonantman.com"
PORT = 5555  # DHO814 confirmed; DG902 Pro assumed same — verify with a bare *IDN? first.


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

    def arm_single(self, trig_ch, level, slope="POSitive", mdepth=1_000_000, tb_scale=0.01):
        self.write(":RUN")
        self.write(f":ACQuire:MDEPth {mdepth}")
        self.write(":TIMebase:MAIN:MODE MAIN")
        self.write(f":TIMebase:MAIN:SCALe {tb_scale}")
        self.write(":TIMebase:MAIN:OFFSet 0")
        self.write(":TRIGger:MODE EDGE")
        self.write(f":TRIGger:EDGE:SOURce CHANnel{trig_ch}")
        self.write(f":TRIGger:EDGE:SLOPe {slope}")
        self.write(f":TRIGger:EDGE:LEVel {level}")
        self.write(":TRIGger:SWEep NORMal")
        time.sleep(0.3)
        self.write(":SINGle")

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

    def __init__(self, host=AWG_HOST, port=PORT, timeout=10):
        super().__init__(host, port, timeout)

    def output(self, on, ch=1):
        self.write(f":OUTPut{ch} {'ON' if on else 'OFF'}")

    def set_highz(self, ch=1):
        # High-Z so commanded amplitude == amplitude at the pin (see class docstring).
        self.write(f":OUTPut{ch}:IMPedance INFinity")

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
