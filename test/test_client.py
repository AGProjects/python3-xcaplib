# Copyright (C) 2008-2009 AG Projects. See LICENSE for details.
#

from __future__ import with_statement
from urllib2 import URLError
from xcaplib.client import XCAPClient, Document
from xcaplib.error import HTTPError, AlreadyExists

class must_raise:
    """
    >>> with must_raise(Exception):
    ...    # this code block must raise an exception
    ...    x = 2+2
    Traceback (most recent call last):
     ...
    AssertionError: expecting exception Exception

    The exception raised must be of the proper type
    >>> with must_raise(ValueError):
    ...     1/0
    Traceback (most recent call last):
     ...
    ZeroDivisionError: integer division or modulo by zero

    The parameter of must_raise is a base class of the errors that should be suppressed
    >>> with must_raise(ArithmeticError):
    ...     1/0 # ZeroDivisionError is a subclass of ArithmeticError
    """

    def __init__(self, klass, **kwargs):
        self.klass = klass
        self.kwargs = kwargs

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        assert exc_type is not None, 'expecting exception %s' % self.klass.__name__
        if issubclass(exc_type, self.klass):
            for (k, v) in self.kwargs.items():
                if getattr(exc_value, k, None)!=v:
                    return False
            return True # suppress the exception

def main():
    root = 'http://10.1.1.3:8000/xcap-root'
    xcap_user_id = 'sip:alice@example.com'
    password = '123'
    client = XCAPClient(root, xcap_user_id, password=password)

    document = file('examples/resource-lists.xml').read()

    # put the whole document
    client.put('resource-lists', document)

    # get the whole document
    got = client.get('resource-lists')

    # it must be the same
    assert document==got, (document, got)

    # get an element:
    res = client.get('resource-lists', '/resource-lists/list/entry/display-name')
    assert res == '<display-name>Bill Doe</display-name>', res

    # get an attribute:
    res = client.get('resource-lists', '/resource-lists/list/entry/@uri')
    assert res == 'sip:bill@example.com', res

    # element operations:
    bob_uri = 'sip:bob@example.com'
    node_selector = '/resource-lists/list/entry[@uri="%s"]' % bob_uri

    # try to replace an element (when there isn't one)
    bob1 = '<entry uri="%s"><display-name>The Bob</display-name></entry>' % bob_uri
    with must_raise(HTTPError, status=404):
        print client.replace('resource-lists', bob1, node_selector)

    # insert an element
    bob2 = '<entry uri="%s"/>' % bob_uri
    res = client.insert('resource-lists', bob2, node_selector, etag=res.etag)
    assert res.status == 201, (res.status, res)

    # insert an element (when there's already one)
    with must_raise(AlreadyExists):
        print client.insert('resource-lists', bob2, node_selector)

    # replace an element, check etag by the way, it should be equal to that of the last result
    res = client.put('resource-lists', bob1, node_selector, etag=res.etag)
    assert res.status == 200, (res.status, res)

    # delete an element
    res = client.delete('resource-lists', node_selector, etag=res.etag)
    assert res.status == 200, (res.status, res)

    # common http errors:
    with must_raise(HTTPError, status=404):
        print client.delete('resource-lists', node_selector)

    # connection errors:
    client2 = XCAPClient('http://www.fdsdfgh.com:32452', xcap_user_id)
    with must_raise(URLError):
        client2.get('resource-lists')

    # https and authentication:
    with must_raise(HTTPError, status=401):
        XCAPClient(root, xcap_user_id, 'invalid-password').get('org.openxcap.watchers')

    watchers = XCAPClient(root, xcap_user_id, password).get('org.openxcap.watchers')
    assert isinstance(watchers, Document), `watchers`
    assert watchers.content_type == 'application/xml', watchers.content_type

    # conditional GET:
    client.put('resource-lists', document)
    got = client.get('resource-lists')    
    assert got==document, (document, got)
    etag = got.etag
    
    got2 = client.get('resource-lists', etag=etag)
    assert document==got2, (document, got2)

    with must_raise(HTTPError, status=412):
        print client.get('resource-lists', etag=etag + 'xxx')

    # conditional DELETE:
    with must_raise(HTTPError, status=412):
        print client.delete('resource-lists', etag=etag+'yyy')

    client.delete('resource-lists', etag=etag)

if __name__ == '__main__':
    main()
