# Copyright (C) 2008-2009 AG Projects. See LICENSE for details.
#

"""Extends standard socket with "dump traffic" feature"""
import sys
from socket import _realsocket

LOG_FILE = sys.stderr

class recv_buffer:
    socket = None
    buf = ''

    @classmethod
    def flush(cls):
        if cls.socket and cls.buf:
            cls.socket.log_recv(cls.buf)
        cls.socket = None
        cls.buf = ''

    @classmethod
    def append(cls, socket, data):
        if socket is cls.socket:
            cls.buf += data
        else:
            cls.flush()
            cls.buf = data
            cls.socket = socket

flush = recv_buffer.flush

class logging_socket(_realsocket):

    def log_recv(self, data):
        params = self.getsockname() + self.getpeername() + (len(data), data)
        LOG_FILE.write('%s:%s <-- %s:%s [%s]\n%s\n' % params)

    def __log_recv(self, data):
        recv_buffer.append(self, data)

    def __log_send(self, data):
        flush()
        params = self.getsockname() + self.getpeername() + (len(data), data)
        LOG_FILE.write('%s:%s --> %s:%s [%s]\n%s\n' % params)

    def close(self):
        flush()
        _realsocket.close(self)

    def recv(self, bufsize, flags=0):
        result = _realsocket.recv(self, bufsize)
        self.__log_recv(result)
        return result

    def send(self, data, flags=0):
        result = _realsocket.send(self, data, flags)
        self.__log_send(data[:result])
        return result

    def sendall(self, data, flags=0):
        result = _realsocket.sendall(self, data, flags)
        self.__log_send(data)
        return result
    # XXX for tcp there's also recv_into
    # QQQ for udp there're also recvfrom, recvfrom_into, sendto

def _install():
    import socket
    socket._realsocket = logging_socket

