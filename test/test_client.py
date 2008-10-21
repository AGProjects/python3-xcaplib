from __future__ import with_statement
import sys
sys.path[0:0] = ['..']
from xcaplib.client import *
from xcaplib.xcapclient import Account, read_xcapclient_cfg

class Result(list):
    def __iadd__(self, other):
        self.append(other)
        return self

class must_raise:

    default_args = ['code']

    def __init__(self, klass, *args, **kwargs):
        self.klass = klass
        self.kwargs = kwargs
        for (k, v) in zip(self.default_args, args):
            self.kwargs[k] = v

    def __enter__(self):
        self.result = Result()
        return self.result

    def __exit__(self, exc_type, exc_value, traceback):
        if self.result:
            print self.result
        if exc_type is None:
            assert False, 'expecting exception %s' % self.klass.__name__
        elif issubclass(exc_type, self.klass):
            for (k, v) in self.kwargs.items():
                if getattr(exc_value, k, None)!=v:
                    return False
            return True

if __name__ == '__main__':

    root = 'http://127.0.0.1:8000'
    user = 'alice@example.com'
    password = '123'
    client = XCAPClient(root, user, password=password)

    document = file('../examples/resource-lists.xml').read()

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

    # replace an element (when there isn't one)
    bob1 = '<entry uri="%s"><display-name>The Bob</display-name></entry>' % bob_uri
    with must_raise(HTTPError, 404) as r:
        r += client.replace('resource-lists', bob1, node_selector)

    # insert an element
    bob2 = '<entry uri="%s"/>' % bob_uri
    res = client.insert('resource-lists', bob2, node_selector, etag=res.etag)
    assert res.code == 201, (res.code, res)

    # insert an element (when there's already one)
    with must_raise(AlreadyExists) as r:
        r += client.insert('resource-lists', bob2, node_selector)

    # replace an element, check etag by the way, it should be equal to that of last result
    res = client.put('resource-lists', bob1, node_selector, etag=res.etag)
    assert res.code == 200, (res.code, res)

    # delete an element
    res = client.delete('resource-lists', node_selector, etag=res.etag)
    assert res.code == 200, (res.code, res)

    # common http errors:
    with must_raise(HTTPError, 404) as r:
        r += client.delete('resource-lists', node_selector)

    # connection errors:
    client2 = XCAPClient('http://www.fdsdfgh.com:32452', user)
    with must_raise(URLError):
        client2.get('resource-lists')

    read_xcapclient_cfg()
    # https and authentication:
    with must_raise(HTTPError, 401):
        XCAPClient(Account.xcap_root, user, 'invalid-password').get('watchers')

    watchers = XCAPClient(Account.xcap_root, user, password).get('watchers')
    assert isinstance(watchers, Document), `watchers`
    assert watchers.content_type == 'application/xml', watchers.content_type

    # conditional GET:
    client.put('resource-lists', document)
    got = client.get('resource-lists')    
    assert got==document, (document, got)
    etag = got.etag
    
    got2 = client.get('resource-lists', etag=etag)
    assert document==got2, (document, got2)

    with must_raise(HTTPError, 412) as r:
        r += client.get('resource-lists', etag=etag + 'xxx')

    # conditional DELETE:
    with must_raise(HTTPError, 412) as r:
        r += client.delete('resource-lists', etag=etag+'yyy')

    client.delete('resource-lists', etag=etag)
