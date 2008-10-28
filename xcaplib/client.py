from xcaplib import __version__
from xcaplib.httpclient import HTTPClient
from xcaplib.error import HTTPError, AlreadyExists

__all__ = ['Resource',
           'Document',
           'Element',
           'AttributeValue',
           'NSBindings',
           'XCAPClient']

DEFAULT_HEADERS = {'User-Agent': 'python-xcaplib/%s' % __version__}

class Resource(str):
    """Result of XCAP GET request: document + etag"""

    def __new__(cls, source, _etag, _content_type=None, _response=None):
        return str.__new__(cls, source)

    def __init__(self, _source, etag, content_type=None, response=None):
        self.etag = etag
        if content_type is not None:
            self.content_type = content_type
        self.response = response

    @staticmethod
    def get_class_for_type(content_type):
        "For given content-type, return an appropriate subclass of Resource"
        if content_type == Element.content_type:
            return Element
        elif content_type == AttributeValue.content_type:
            return AttributeValue
        elif content_type == NSBindings.content_type:
            return NSBindings
        else:
            return lambda source, etag, response: Document(source, etag, content_type, response)

    @staticmethod
    def get_content_type_for_node(node):
        "For given node selector, return an appropriate content-type for PUT request"
        if node is None:
            return None
        elif node.endswith('namespace::*'):
            return NSBindings.content_type
        elif node[node.rindex('/')+1:][:1] == '@':
            return AttributeValue.content_type
        else:
            return Element.content_type

    def __eq__(self, other):
        try:
            return str.__eq__(self, other) and self.etag==other.etag and self.content_type==other.content_type
        except AttributeError:
            return True

    def __ne__(self, other):
        try:
            return str.__ne__(self, other) or self.etag!=other.etag or self.content_type!=other.content_type
        except AttributeError:
            return False

class Document(Resource):
    content_type = None # depends on the application

class Element(Resource):
    content_type = 'application/xcap-el+xml'

class AttributeValue(Resource):
    content_type = 'application/xcap-att+xml'

class NSBindings(Resource):
    content_type = 'application/xcap-ns+xml'

def get_path(xcap_user_id, application, node, globaltree=False, filename=None):
    if filename is None:
        filename = 'index'
    if globaltree:
        path = "/%s/global/%s" % (application, filename)
    else:
        path = "/%s/users/%s/%s" % (application, xcap_user_id, filename)
    if node:
        if path[-1:]!='/':
            path += '/'
        path += '~~' + node
    return path

class XCAPClientBase(object):

    HTTPClient = HTTPClient

    def __init__(self, root, sip_address, password=None, auth=None):
        self.root = root
        if self.root[-1:] == '/':
            self.root = self.root[:-1]
        self.sip_address = sip_address
        if sip_address[:4] == 'sip:':
            sip_address = sip_address[4:]
        username, domain = sip_address.split('@', 1)
        self.con = self.HTTPClient(self.root, username, domain, password, auth=auth)

    def _update_headers(self, headers):
        if headers is None:
            headers = {}
        for k, v in DEFAULT_HEADERS.iteritems():
            headers.setdefault(k, v)
        return headers

    def get_url(self, application, node, **kwargs):
        return (self.root or '') + get_path(self.sip_address, application, node, **kwargs)

    def _get(self, application, node=None, etag=None, headers=None, **kwargs):
        headers = self._update_headers(headers)
        path = get_path(self.sip_address, application, node, **kwargs)
        return self.con.request('GET', path, headers=headers, etag=etag)

    def _put(self, application, resource, node=None, etag=None, headers=None, **kwargs):
        headers = self._update_headers(headers)
        path = get_path(self.sip_address, application, node, **kwargs)
        if 'Content-Type' not in headers:
            content_type = Resource.get_content_type_for_node(node)
            if content_type:
                headers['Content-Type'] = content_type
        return self.con.request('PUT', path, headers, resource, etag=etag)

    def _delete(self, application, node=None, etag=None, headers=None, **kwargs):
        headers = self._update_headers(headers)
        path = get_path(self.sip_address, application, node, **kwargs)
        return self.con.request('DELETE', path, etag=etag, headers=headers)

def make_resource_from_httpresponse(response):
    if 200 <= response.status <= 299:
        content_type = response.headers.get('content-type')
        klass = Resource.get_class_for_type(content_type)
        return klass(response.body, response.etag, response)
    else:
        raise HTTPError(response)

class XCAPClient(XCAPClientBase):

    def get(self, *args, **kwargs):
        "Return Resource instance on success, raise HTTPError otherwise"
        return make_resource_from_httpresponse(self._get(*args, **kwargs))

    def put(self, *args, **kwargs):
        "Return HTTPResponse on success, raise HTTPError otherwise"
        response = self._put(*args, **kwargs)
        if 200 <= response.status <= 299:
            return response
        raise HTTPError(response)

    def delete(self, *args, **kwargs):
        "Return HTTPResponse on success, raise HTTPError otherwise"
        response = self._delete(*args, **kwargs)
        if 200 <= response.status <= 299:
            return response
        raise HTTPError(response)

    def replace(self, application, resource, node=None, etag=None, **kwargs):
        """check that the node already exists. if so, PUT.
        Return (old_resource, reply to PUT)
        """
        # XXX pointless function, since in real usage we'll have etag and just
        # do conditional PUT?
        old = self.get(application, node, etag, **kwargs)
        res = self.put(application, resource, node, old.etag, **kwargs)
        return (old, res)

    def insert_document(self, application, resource, **kwargs):
        """check that the resource doesn't exists. if so, PUT.

        Since 404 doesn't return ETag, it is not reliable (someone could
        do PUT after our GET and we will replace the document, instead of inserting.
        """
        try:
            self.get(application, **kwargs)
        except HTTPError, ex:
            if ex.status == 404:
                # how to ensure insert?
                # 1. make openxcap to supply fixed tag into 404, like ETag: "none"
                # and understand If-Match: "none" as intent to insert.
                # 2. If-None-Match: *, what does it do?
                return self.put(application, resource, **kwargs)
        else:
            raise AlreadyExists(application)

    def insert(self, application, resource, node=None, etag=None, retries=5, **kwargs):
        """check that the resource doesn't exists. if so, PUT.
        1. Get the whole document. This is needed for etag.
        2. If node supplied, check that that node doesn't exists (it
           could be done locally, but we're doing it via another GET to
           the server)
        3. PUT the resource.
        """
        if node is None:
            if etag is not None:
                raise ValueError('Cannot PUT the document, reliably. Set etag to None')
            return self.insert_document(application, resource, **kwargs)

        while retries>=0:
            retries -= 1
            document = self.get(application, None, etag, **kwargs)
            try:
                element = self.get(application, node, document.etag, **kwargs)
            except HTTPError, ex:
                if etag is None and ex.status == 412:
                    continue
                elif ex.status == 404:
                    try:
                        return self.put(application, resource, node, document.etag, **kwargs)
                    except HTTPError, ex:
                        if etag is None and ex.status == 412:
                            continue
                        else:
                            raise
                else:
                    raise
            else:
                raise AlreadyExists(application, node)


