# simple_tcp_server
Simple TCP server framework.

## Installation

```bash
pip install simple_tcp_server
```

## Usage

```python
from simple_tcp_server import SimpleTcpServer, SimpleTcpClient
import threading
import time

HOST = "127.0.0.1"
PORT = 9999

def is_prime(msg: bytes) -> bytes:
    n = int(msg.decode())
    if n < 2:
        return b"$"
    for i in range(2, int(n**0.5)+1):
        if n % i == 0:
            return b"$"
    return b"$$"

server = SimpleTcpServer(HOST, PORT, is_prime, quit_token=b"quit")
t = threading.Thread(target=server.mainloop, daemon=True)
t.start()

time.sleep(0.2)

client = SimpleTcpClient(HOST, PORT)

numbers = [b"2", b"10", b"17", b"97", b"1234567"]
for n in numbers:
    res = client.request(n)
    print(f"{n}: {res}")

# close server by quit_token
client.request(b"quit")
for n in numbers:
    res = client.request(n)
    print(f"{n}: {res}")

client.close()
```
