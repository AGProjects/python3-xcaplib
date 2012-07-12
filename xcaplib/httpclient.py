# Copyright (C) 2008-2012 AG Projects. See LICENSE for details.
#

"""Make HTTP requests. Thin wrapper around urllib2"""


__all__ = ['HTTPClient', 'HTTPResponse']


import httplib
import socket
import urllib
import urllib2


class Address(str):
    def __init__(self, value):
        self.refcount = 0

class HostCache(object):
    def __init__(self):
        self.hostmap = {}

    def get(self, host):
        return str(self.hostmap[host])

    def lookup(self, host):
        try:
            address = self.hostmap[host]
        except KeyError:
            try:
                address = self.hostmap.setdefault(host, Address(next(sa[0] for family, socktype, proto, cname, sa in socket.getaddrinfo(host, 0, 0, 0, socket.SOL_TCP))))
            except socket.gaierror:
                address = self.hostmap.setdefault(host, Address(host))
        address.refcount += 1
        return str(address)

    def release(self, host):
        address = self.hostmap[host]
        address.refcount -= 1
        if address.refcount == 0:
            del self.hostmap[host]

HostCache = HostCache()


class HTTPConnection(httplib.HTTPConnection):
    def connect(self):
        address = HostCache.get(self.host)
        self.sock = socket.create_connection((address, self.port), self.timeout, self.source_address)
        if self._tunnel_host:
            self._tunnel()

class HTTPSConnection(httplib.HTTPSConnection):
    def connect(self):
        import ssl
        address = HostCache.get(self.host)
        sock = socket.create_connection((address, self.port), self.timeout, self.source_address)
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
        self.sock = ssl.wrap_socket(sock, self.key_file, self.cert_file)

class HTTPHandler(urllib2.HTTPHandler):
    def http_open(self, req):
        return self.do_open(HTTPConnection, req)

class HTTPSHandler(urllib2.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(HTTPSConnection, req)


class HTTPRequest(urllib2.Request):
    """Hack urllib2.Request to support PUT and DELETE methods."""

    def __init__(self, url, method="GET", data=None, headers={}, origin_req_host=None, unverifiable=False):
        urllib2.Request.__init__(self, url, data, headers, origin_req_host, unverifiable)
        self.url = url
        self.method = method

    def get_method(self):
        return self.method

    def format(self):
        s = '%s %s\n' % (self.get_method(), self.get_full_url())
        s += '\n'.join(("%s: %s" % x for x in self.header_items()))
        return s


class HTTPResponse(object):
    def __init__(self, url, status, reason, headers, body):
        self.url = url
        self.status = status
        self.reason = reason
        self.headers = headers if headers is not None else {}
        self.body = body

    def __str__(self):
        result = "%s %s <%s>" % (self.status, self.reason, self.url)
        for k, v in self.headers.items():
            result += '\n%s: %s' % (k, v)
        if self.body:
            result += '\n\n'
            result += self.body
            result += '\n'
        return result

    @property
    def etag(self):
        etag = self.headers.get('ETag')
        if etag is None:
            return None
        if len(etag) > 1 and etag[0] == etag[-1] == '"':
            return etag[1:-1]
        else:
            raise ValueError('Cannot parse etag header value: %r' % etag)

    @classmethod
    def from_HTTPError(cls, response):
        if response.fp is not None:
            length = int(response.hdrs.get('content-length') or -1)
            body = response.fp.read(length)
        else:
            body = ''
        return cls(response.filename, response.code, response.msg, response.hdrs, body)

    @classmethod
    def from_addinfourl(cls, response):
        length = int(response.headers.get('content-length') or -1)
        return cls(response.url, response.code, response.msg, response.headers, response.fp.read(length))


class HTTPClient(object):
    def __init__(self, base_url, username, domain, password=None):
        self.base_url = base_url
        if self.base_url[-1:] != '/':
            self.base_url += '/'
        password_manager = urllib2.HTTPPasswordMgr()
        password_manager.add_password(domain, self.base_url, username, password)
        self.opener = urllib2.build_opener(HTTPHandler, HTTPSHandler, urllib2.HTTPDigestAuthHandler(password_manager), urllib2.HTTPBasicAuthHandler(password_manager))

    def request(self, method, path, headers=None, data=None, etag=None, etagnot=None):
        """Make HTTP request. Return HTTPResponse instance.

        Will never raise urllib2.HTTPError, but may raise other exceptions, such
        as urllib2.URLError or httplib.HTTPException
        """
        if path[:1]=='/':
            path = path[1:]
        if headers is None:
            headers = {}
        if etag is not None:
            headers['If-Match'] = '"%s"' % etag if etag!='*' else '*' # XXX use quoteString instead?
        if etagnot is not None:
            headers['If-None-Match'] = ('"%s"' % etagnot) if etagnot!='*' else '*'
        url = self.base_url+path
        req = HTTPRequest(url, method=method, headers=headers, data=data)
        host, port = urllib.splitport(req.get_host())
        HostCache.lookup(host)
        try:
            response = self.opener.open(req)
            if isinstance(response, urllib2.HTTPError):
                return HTTPResponse.from_HTTPError(response)
            elif isinstance(response, urllib2.addinfourl):
                return HTTPResponse.from_addinfourl(response)
            else:
                raise RuntimeError('urllib2.open returned %r' % response)
        except urllib2.HTTPError, e:
            # Workaround for bug in urllib2 which doesn't reset the retry count
            # when a negative, but different that 401 or 407, response is
            # received. -Luci
            if e.code not in (401, 407):
                for handler in (handler for handler in self.opener.handlers if isinstance(handler, (urllib2.HTTPDigestAuthHandler, urllib2.ProxyDigestAuthHandler))):
                    handler.reset_retry_count()
            return HTTPResponse.from_HTTPError(e)
        finally:
            HostCache.release(host)


