from typing import Callable, Tuple
import socket
import time
from . import Utils

_BytesToBytes = Callable[[bytes], bytes]
_ClientAddress = Tuple[str, int]

class SimpleTcpServer:
    def __init__(self, 
            host: str, 
            port: int, 
            worker_function: _BytesToBytes,
            quit_token: bytes, 
            max_listen: int = 5, 
            client_timeout: float = 10.0) -> None:
        
        self.host = host
        self.port = port
        self.worker_function = worker_function
        self.quit_token = quit_token
        self.max_listen = max_listen
        self.client_timeout = client_timeout
        self.max_buffer = Utils.MAX_BUFFER

        # System running status
        self.running = True

        # Initialize server_socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(self.max_listen)
        self.server_socket.setblocking(False)  # Non-blocking mode

        # Connection pool
        self.conn_pool: dict[_ClientAddress, socket.socket] = dict()
        self.conn_buff: dict[_ClientAddress, bytes] = dict()  # Buffer pool
        self.last_seen: dict[_ClientAddress, float] = dict()  # Record the time of the last received message

    # Close an existing connection
    # The connection must exist
    def _conn_close(self, addr: _ClientAddress):
        self.conn_pool[addr].close()
        del self.conn_pool[addr]
        del self.conn_buff[addr]
        del self.last_seen[addr]

    # Handle a new client connection
    def _handle(self, conn: socket.socket, addr: _ClientAddress):

        # Client address conflict detected
        # Force close the old client connection
        if self.conn_pool.get(addr) is not None:
            self._conn_close(addr)
        
        # No address conflict now, add to the connection list
        conn.setblocking(False)
        self.conn_pool[addr] = conn        # Socket
        self.conn_buff[addr] = b""         # Buffer
        self.last_seen[addr] = time.time() # Initial connection counts as a message

    # Attempt to accept new connections
    def _try_accept(self):
        try:
            conn, addr = self.server_socket.accept() 
            self._handle(conn, addr)
        except BlockingIOError:  # No new connection found
            pass
    
    # Attempt to receive data from a connection
    # Return True if the connection is dead
    def _acquire_once(self, addr: _ClientAddress) -> bool:
        conn = self.conn_pool[addr]
        died = False  # Assume alive initially
        try:
            msg = conn.recv(self.max_buffer)
            if msg == b"":  # Empty message means the peer disconnected
                died = True

            # Append non-empty message
            else:
                self.conn_buff[addr] += msg 
                self.last_seen[addr] = time.time()

        # Blocking error means no data available (still alive), other errors mean dead
        except Exception as err: 
            died = not isinstance(err, BlockingIOError)
        return died
    
    # Count occurrences of a substring in bytes
    def _count_bytes(self, data: bytes, sub: bytes) -> int:
        if not sub:
            return 0
        i = 0  # Start position
        count = 0
        len_sub = len(sub)
        while (i := data.find(sub, i)) != -1:  # No overlapping matches
            count += 1
            i += len_sub
        return count
    
    # Calculate response for a single request and send it
    # Return True if the peer is dead
    def _calc_and_resp(self, addr: _ClientAddress, msg_now: bytes) -> bool:
        msg_get = Utils.unescape(msg_now)

        # Use try-except to prevent worker function crashes
        try:
            ret_ans = self.worker_function(msg_get)
        except Exception as err:
            ret_ans = str(err).encode("utf-8")

        send_ans = Utils.escape(ret_ans)  # Avoid parsing issues with eoq() in data
        died = False  # Check if peer is dead
        try:
            self.conn_pool[addr].sendall(send_ans + Utils.eoq())
            self.last_seen[addr] = time.time()  # Sending counts as peer activity
        except Exception:
            died = True
        return died  # Normal sendall means peer is alive

    # Attempt to send a response to a client
    # Return True if the connection is dead
    def _response_once(self, addr: _ClientAddress) -> bool:
        buff = self.conn_buff[addr]

        # No data received yet, cannot determine connection status
        if len(buff) == 0:
            return False
        
        # Not a complete message, check integrity
        # All messages end with $$, no consecutive $$ inside the message
        if self._count_bytes(buff, Utils.eoq()) == 0:
            return False
        
        # Process the current message
        msg_now, self.conn_buff[addr] = buff.split(Utils.eoq(), maxsplit=1)
        assert len(msg_now) != 0

        # Quit token detected
        # Prepare to stop the server
        if msg_now == self.quit_token:
            self.running = False

        # Calculate response and send it back
        # Return True if peer is dead
        return self._calc_and_resp(addr, msg_now)

    # Return True if the connection should be closed
    # False otherwise
    def _chk_timeout(self, addr: _ClientAddress) -> bool:
        if time.time() - self.last_seen[addr] >= self.client_timeout:
            return True  # Caller handles resource cleanup
        return False

    # Perform a worker operation on all clients
    # Worker returns True if client is dead
    def _chk_all_temp(self, worker: Callable[[_ClientAddress], bool]):
        for addr in self._all_addr():  # Iterate all connections
            if worker(addr):          # Apply unified operation to all addresses
                self._conn_close(addr)

    # Attempt to receive data from all connections
    # Clean up dead connections
    def _acquire_all(self):
        self._chk_all_temp(self._acquire_once)

    # Attempt to send responses to all eligible clients
    # Clean up dead connections
    def _response_all(self):
        self._chk_all_temp(self._response_once)

    # Get all current client addresses
    def _all_addr(self) -> list[_ClientAddress]:
        return list(self.conn_pool.keys())

    # Release resources
    # Kick all clients offline and free buffers
    def _kick_all(self):
        for addr in self._all_addr():
            self._conn_close(addr)

    # Kick all timed-out clients
    def _kick_timeout(self):
        self._chk_all_temp(self._chk_timeout)

    # Start the main server loop (single-threaded)
    def mainloop(self):
        while self.running:
            self._try_accept()    # Attempt to accept new connections
            self._acquire_all()   # Attempt to receive data from existing connections
            self._response_all()  # Attempt to send responses to all clients
            self._kick_timeout()  # Kick inactive clients
        self._kick_all()
