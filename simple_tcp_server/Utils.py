import re

# 单字节标志符号
half_eoq = b"$"

# 替换转义字符
def replace_octal_bytes(data: bytes) -> bytes:
    return re.sub(
        re.escape(half_eoq) + rb"(\d{3})",
        lambda m: bytes([int(m[1], 8)]),
        data
    )

# 处理转义字符
def anti_escape(msg:bytes) -> bytes:
    return replace_octal_bytes(msg)

# 将字符串中的 _eoq() 进行特殊处理
# 本质上就是补上一个三位八进制数
def escape(msg:bytes) -> bytes:
    number = f"{half_eoq[0]:03o}".encode()
    return msg.replace(half_eoq, half_eoq + number)


# 获取结束标志（长度总为 2）
def eoq() -> bytes:
    return half_eoq + half_eoq
