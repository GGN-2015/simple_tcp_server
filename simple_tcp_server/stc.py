import socket
from typing import Optional
from . import Utils

class SimpleTcpClient:
    def __init__(self, host: str, port: int):
        # Protocol configuration
        self.max_buffer = Utils.MAX_BUFFER

        # Connection status
        self.connected = False

        # Initialize socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect((host, port))
            self.connected = True  # Connection succeeded
        except Exception:
            self.connected = False

        self.buffer = b""

    # Auto-close on destruction
    def __del__(self):
        self.close()

    # Safe close
    def close(self):
        self.connected = False
        try:
            self.sock.close()
        except Exception:
            pass

    # Send and receive (persistent connection, no exceptions thrown)
    # Return None if connection is lost
    def request(self, msg: bytes) -> Optional[bytes]:
        # Already disconnected
        if not self.connected:
            return None

        # 1. Send data (protected by try)
        try:
            send_msg = Utils.escape(msg) + Utils.eoq()
            self.sock.sendall(send_msg)
        except Exception:
            self.close()
            return None

        # 2. Receive data in loop (protected by try)
        while (Utils.eoq() not in self.buffer) and self.connected:
            try:
                data = self.sock.recv(self.max_buffer)
                if not data:  # Server closed the connection
                    self.close()
                    return None
                self.buffer += data
            except Exception:
                self.close()
                return None

        # 3. Parse message
        resp, self.buffer = self.buffer.split(Utils.eoq(), 1)
        return Utils.unescape(resp)
