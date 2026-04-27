import re

# Single-byte flag symbol
HALF_EOQ = b"$"

# Buffer size
MAX_BUFFER = 262144

# Replace escaped octal bytes
def replace_octal_bytes(data: bytes) -> bytes:
    return re.sub(
        re.escape(HALF_EOQ) + rb"(\d{3})",
        lambda m: bytes([int(m[1], 8)]),
        data
    )

# Process escape characters
def unescape(msg: bytes) -> bytes:
    return replace_octal_bytes(msg)

# Special handling for _eoq() sequences in the message
# Essentially appends a 3-digit octal number
def escape(msg: bytes) -> bytes:
    octal_str = f"{HALF_EOQ[0]:03o}".encode()
    return msg.replace(HALF_EOQ, HALF_EOQ + octal_str)

# Get end-of-query marker (always length 2)
def eoq() -> bytes:
    return HALF_EOQ + HALF_EOQ
