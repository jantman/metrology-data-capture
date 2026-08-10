"""Minimal SCPI client for the Rigol DHO814 oscilloscope over LAN (raw socket, port 5555).

Used to reverse-engineer the Mxmoonfree LS-20 caliper data port: configure channels,
single-shot capture, and pull raw waveform memory for both channels for offline decode.
"""
import socket
import time

HOST = "rigol-oscope.jasonantman.com"
PORT = 5555


class Scope:
    def __init__(self, host=HOST, port=PORT, timeout=10):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass

    def write(self, cmd):
        self.sock.sendall((cmd + "\n").encode())

    def _read_until_newline(self):
        buf = bytearray()
        while True:
            b = self.sock.recv(1)
            if not b:
                break
            if b == b"\n":
                break
            buf += b
        return buf

    def query(self, cmd):
        self.write(cmd)
        return self._read_until_newline().decode(errors="replace").strip()

    def read_block(self):
        """Read an IEEE 488.2 definite-length block: #NLLLL<bytes>\\n"""
        # find leading '#'
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
        # consume trailing newline if present
        try:
            self.sock.recv(1)
        except Exception:
            pass
        return bytes(data)

    def query_block(self, cmd):
        self.write(cmd)
        return self.read_block()

    def screenshot(self, path):
        data = self.query_block(":DISPlay:DATA? PNG")
        with open(path, "wb") as f:
            f.write(data)
        return len(data)


if __name__ == "__main__":
    s = Scope()
    print("IDN:", s.query("*IDN?"))
    s.close()
