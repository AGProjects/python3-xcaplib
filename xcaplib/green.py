
"""XCAP client for use from eventlib green threads.

The HTTP(S) requests themselves are done with the standard library (the same
code as the non-green client) in a worker thread, while the calling green
thread waits for the result. This way a slow DNS lookup, TCP connect, TLS
handshake or server response never blocks the eventlib hub (which, when using
the twisted hub, is the twisted reactor thread and stalls everything else).
"""

import threading

from eventlib.api import get_hub

from xcaplib import httpclient
from xcaplib import client


__all__ = ['HTTPClient', 'XCAPClient']


# Used when the caller does not specify a timeout, so that a request can never
# hang forever and hold a worker thread and the client's request lock.
DEFAULT_TIMEOUT = 30


def _call_in_thread(func, *args, **kw):
    """Run func in a worker thread and wait for its result from a green thread"""
    if getattr(get_hub(), 'uses_twisted_reactor', False):
        from twisted.internet.threads import deferToThread
        from eventlib.twistedutil import block_on
        return block_on(deferToThread(func, *args, **kw))
    else:
        from eventlib import tpool
        return tpool.execute(func, *args, **kw)


class HTTPClient(httpclient.HTTPClient):
    def __init__(self, *args, **kw):
        super(HTTPClient, self).__init__(*args, **kw)
        # The opener (its digest authentication handler in particular) is not
        # thread safe, so requests made through the same client are serialized.
        self._request_lock = threading.Lock()

    def _locked_request(self, *args, **kw):
        with self._request_lock:
            return super(HTTPClient, self).request(*args, **kw)

    def request(self, method, path, headers=None, data=None, etag=None, etagnot=None, timeout=None):
        if timeout is None:
            timeout = DEFAULT_TIMEOUT
        return _call_in_thread(self._locked_request, method, path, headers=headers, data=data, etag=etag, etagnot=etagnot, timeout=timeout)


class XCAPClient(client.XCAPClient):
    HTTPClient = HTTPClient

