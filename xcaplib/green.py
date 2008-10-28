from eventlet.green.urllib2 import build_opener
from xcaplib import httpclient
from xcaplib import client

class HTTPClient(httpclient.HTTPClient):
    def build_opener(self, *args):
        return build_opener(*args)

class XCAPClient(client.XCAPClient):
    HTTPClient = HTTPClient

