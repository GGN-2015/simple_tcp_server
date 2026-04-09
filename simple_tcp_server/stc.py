import socket
from typing import Optional
from . import Utils

class SimpleTcpClient:
    def __init__(self, host: str, port: int):
        # 协议配置（必须与服务端一致）
        self.max_buffer = 4096

        # 连接状态
        self.connected = False

        # 初始化 socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect((host, port))
            self.connected = True  # 连接成功
        except Exception:
            self.connected = False

        self.buffer = b""

    # 析构时自动关闭
    def __del__(self):
        self.close()

    # 安全关闭
    def close(self):
        self.connected = False
        try:
            self.sock.close()
        except Exception:
            pass

    # 发送并接收（长连接，不抛异常）
    # 如果连接断开，返回 None
    def request(self, msg: bytes) -> Optional[bytes]:
        # 已经断了
        if not self.connected:
            return None

        # 1. 发送数据（try 保护）
        try:
            send_msg = Utils.escape(msg) + Utils.eoq()
            self.sock.sendall(send_msg)
        except Exception:
            self.close()
            return None

        # 2. 循环接收数据（try 保护）
        while (Utils.eoq() not in self.buffer) and self.connected:
            try:
                data = self.sock.recv(self.max_buffer)
                if not data:  # 服务器关闭连接
                    self.close()
                    return None
                self.buffer += data
            except Exception:
                self.close()
                return None

        # 3. 解析消息
        resp, self.buffer = self.buffer.split(Utils.eoq(), 1)
        return Utils.anti_escape(resp)
