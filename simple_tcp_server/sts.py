from typing import Callable, Tuple
import socket
import time
from . import Utils

_BytesToBytes  = Callable[[bytes], bytes]
_ClientAddress = Tuple[str, int]

class SimpleTcpServer:
    def __init__(self, 
            host:str, 
            port:int, 
            worker_function:_BytesToBytes,
            quit_token:bytes, 
            max_listen:int=5, 
            client_timeout:float=10.0) -> None:
        
        self.host = host
        self.port = port
        self.worker_function = worker_function
        self.quit_token = quit_token
        self.max_listen = max_listen
        self.client_timeout = client_timeout
        self.max_buffer = 1024

        # 系统运行状态
        self.running = True

        # 初始化 server_socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(self.max_listen)
        self.server_socket.setblocking(False) # 非阻塞模式

        # 连接池
        self.conn_pool:dict[_ClientAddress, socket.socket] = dict()
        self.conn_buff:dict[_ClientAddress, bytes]         = dict() # 缓冲区池子
        self.last_seen:dict[_ClientAddress, float]         = dict() # 记录最晚一次收到消息的时刻

    # 断开一个现有连接
    # 此连接必须存在
    def _conn_close(self, addr:_ClientAddress):
        self.conn_pool[addr].close()
        del self.conn_pool[addr]
        del self.conn_buff[addr]
        del self.last_seen[addr]

    # 处理一个用户入项连接
    def _handle(self, conn:socket.socket, addr:_ClientAddress):

        # 出现了客户端地址冲突
        # 把旧的客户端强制切断
        if self.conn_pool.get(addr) is not None:
            self._conn_close(addr)
        
        # 此时一定没有地址重复的问题, 可以将其加入到地址序列中
        conn.setblocking(False)
        self.conn_pool[addr] = conn        # 套接字
        self.conn_buff[addr] = b""         # 缓冲区
        self.last_seen[addr] = time.time() # 初次连接视为消息

    # 试图发现新的连接
    def _try_accept(self):
        try:
            conn, addr = self.server_socket.accept() 
            self._handle(conn, addr)
        except BlockingIOError: # 没有发现新的连接
            pass
    
    # 试图对一个连接获取数据
    # 返回当前连接是不是真的死了
    def _acquire_once(self, addr:_ClientAddress) -> bool:
        conn = self.conn_pool[addr]
        died = False # 假定还没死
        try:
            msg = conn.recv(self.max_buffer)
            if msg == b"": # 读到一个空消息说明对方死掉了
                died = True

            # 追加非空消息
            else:
                self.conn_buff[addr] += msg 
                self.last_seen[addr] = time.time()

        # 阻塞错误说明对方没写东西，但是还没死, 其他错误说明对方死了
        except Exception as err: 
            died = not isinstance(err, BlockingIOError)
        return died
    
    # 统计 bytes 串出现次数
    def _count_bytes(self, data: bytes, sub: bytes) -> int:
        if not sub:
            return 0
        i = 0 # 初始化位置
        count = 0
        len_sub = len(sub)
        while (i := data.find(sub, i)) != -1: # 不允许重叠
            count += 1
            i += len_sub
        return count
    
    # 计算单次请求结果并发送
    # 如果对方死了返回 True
    def _calc_and_resp(self, addr:_ClientAddress, msg_now:bytes) -> bool:
        msg_get  = Utils.anti_escape(msg_now)

        # 为了避免外包程序报错，需要使用 try 保护
        try:
            ret_ans = self.worker_function(msg_get)
        except Exception as err:
            ret_ans = str(err).encode("utf-8")

        send_ans = Utils.escape(ret_ans) # 避免数据中 eoq() 无法正常解读
        died = False # 检查对方是否死了
        try:
            self.conn_pool[addr].sendall(send_ans + Utils.eoq())
            self.last_seen[addr] = time.time() # 我们发消息也算对方的行为
        except Exception:
            died = True
        return died # 正常 sendall 了说明对方没死

    # 试图给一个客户端写回信
    # 返回当前连接是不是真的死了
    def _response_once(self, addr:_ClientAddress) -> bool:
        buff = self.conn_buff[addr]

        # 当前没有收到任何信息，无从判断这家伙死没死
        if len(buff) == 0:
            return False
        
        # 不是协商消息，检查信息完整性
        # 所有的消息以 $$ 作为结尾，消息内部保证没有连续的 $$
        if self._count_bytes(buff, Utils.eoq()) == 0:
            return False
        
        # 处理当前消息
        msg_now, self.conn_buff[addr] = buff.split(Utils.eoq(), maxsplit=1)
        assert len(msg_now) != 0

        # 检测到了退出标志
        # 需要准备将服务器关停（但是不用马上关停也行）
        if msg_now == self.quit_token:
            self.running = False

        # 计算单次请求结果并发送回去
        # 如果对方死了返回 True
        return self._calc_and_resp(addr, msg_now)

    # 如果想让对方死，那就返回 True
    # 否则就返回 False
    def _chk_timeout(self, addr:_ClientAddress) -> bool:
        if time.time() - self.last_seen[addr] >= self.client_timeout:
            return True # 调用者会自动负责清理资源
        return False

    # 对所有客户端进行一次 worker 操作 
    # 如果客户端死了 worker 操作必须返回 True
    def _chk_all_temp(self, worker:Callable[[_ClientAddress], bool]):
        for addr in self._all_addr(): # 遍历所有连接
            if worker(addr):      # 试图对所有地址对象进行统一操作
                self._conn_close(addr)

    # 试图从每个池子里获取数据
    # 同时清理池子里的死鱼
    def _acquire_all(self):
        self._chk_all_temp(self._acquire_once)

    # 试图给所有可以回信的人
    # 写回信，同时清理池子
    def _response_all(self):
        self._chk_all_temp(self._response_once)

    # 获取当前所有客户端地址
    def _all_addr(self) -> list[_ClientAddress]:
        return list(self.conn_pool.keys())

    # 回收资源
    # 把所有人踢下线（回收缓冲区资源）
    def _kick_all(self):
        for addr in self._all_addr():
            self._conn_close(addr)

    # 把所有超时对象踢下线
    def _kick_timeout(self):
        self._chk_all_temp(self._chk_timeout)

    # 启动服务器主循环（单线程）
    def mainloop(self):
        while self.running:
            self._try_accept()   # 试图发现新的链接
            self._acquire_all()  # 试图从现有池子中获取数据（我们假定池子里都是活的）
            self._response_all() # 试图给所有人写回信
            self._kick_timeout() # 把所有长时间不吱声的人给踢下线
        self._kick_all()
