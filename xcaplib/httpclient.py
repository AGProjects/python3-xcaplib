# Copyright (C) 2008-2009 AG Projects. See LICENSE for details.
#

"""Make HTTP requests. Thin wrapper around urllib2"""
import urllib2

__all__ = ['HTTPClient',
           'HTTPResponse']

class HTTPRequest(urllib2.Request):
    """Hack urllib2.Request to support PUT and DELETE methods."""

    def __init__(self, url, method="GET", data=None, headers={},
                 origin_req_host=None, unverifiable=False):
        urllib2.Request.__init__(self,url,data,headers,origin_req_host,unverifiable)
        self.url = url
        self.method = method

    def get_method(self):
        return self.method

    def format(self):
        s = '%s %s\n' % (self.get_method(), self.get_full_url())
        s += '\n'.join(("%s: %s" % x for x in self.header_items()))
        return s


class HTTPClient(object):

    def build_opener(self, *args):
        return urllib2.build_opener(*args)

    def __init__(self, base_url, username, domain, password=None, auth=None):
        self.base_url = base_url
        if self.base_url[-1:]!='/':
            self.base_url += '/'

        handlers = []

        def add_handler(klass):
            handler = klass()
            #print handler, domain, self.base_url, username, password
            handler.add_password(domain, self.base_url, username, password)
            handlers.append(handler)

        if auth == 'basic':
            add_handler(urllib2.HTTPBasicAuthHandler)
        elif auth == "digest":
            add_handler(urllib2.HTTPDigestAuthHandler)
        elif username is not None and password is not None:
            add_handler(urllib2.HTTPDigestAuthHandler)
            add_handler(urllib2.HTTPBasicAuthHandler)
        self.opener = self.build_opener(*handlers)

    def request(self, method, path, headers=None, data=None, etag=None):
        """Make HTTP request. Return HTTPResponse instance.

        Will never raise urllib2.HTTPError, but may raise other exceptions, such
        as urllib2.URLError or httplib.HTTPException
        """
        if path[:1]=='/':
            path = path[1:]
        if headers is None:
            headers = {}
        if etag is not None:
            headers['If-Match'] = '"' + etag + '"' # XXX use quoteString instead?
        url = self.base_url+path
        req = HTTPRequest(url, method=method, headers=headers, data=data)
        try:
            response = self.opener.open(req)
            if isinstance(response, urllib2.HTTPError):
                return convert_urllib2_HTTPError(response)
            elif isinstance(response, urllib2.addinfourl):
                return convert_urllib_addinfourl(response)
            else:
                raise RuntimeError('urllib2.open returned %r' % response)
        except urllib2.HTTPError, e:
            return convert_urllib2_HTTPError(e)


def parse_etag_header(s):
    if s is None:
        return s
    if len(s)>1 and s[0]=='"' and s[-1]=='"':
        return s[1:-1]
    else:
        raise ValueError('Cannot parse etag header value: %r' % s)


class HTTPResponse(object):

    def __init__(self, url, status, reason, headers, body):
        self.url = url
        self.status = status
        self.reason = reason
        self.headers = headers
        if self.headers is None:
            self.headers = {}
        self.body = body

    @property
    def etag(self):
        return parse_etag_header(self.headers.get('ETag'))

    def __str__(self):
        result = "%s %s <%s>" % (self.status, self.reason, self.url)
        for k, v in self.headers.items():
            result += '\n%s: %s' % (k, v)
        if self.body:
            result += '\n\n'
            result += self.body
            result += '\n'
        return result

def convert_urllib2_HTTPError(x):
    len = x.hdrs.get('content-length')
    if len is not None:
        len = int(len)
    body = x.fp.read(len)
    return HTTPResponse(x.filename, x.code, x.msg, x.hdrs, body)

def convert_urllib_addinfourl(x):
    len = x.headers.get('content-length')
    if len is not None:
        len = int(len)
    return HTTPResponse(x.url, 200, 'OK', x.headers, x.fp.read(len))
