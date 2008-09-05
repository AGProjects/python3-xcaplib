import sys
sys.path[0:0] = ['..']
from xcaplib.client import *
from xcaplib.xcapclient import Account, read_xcapclient_cfg

if __name__ == '__main__':

    root = 'http://127.0.0.1:8000'
    user = 'alice@example.com'
    client = XCAPClient(root, user, password='123')

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
    try:
        res = client.replace('resource-lists', bob1, node_selector)
        assert False, 'should not get there'
    except HTTPError, e:
        if e.code != 404:
            raise

    # insert an element
    bob2 = '<entry uri="%s"/>' % bob_uri
    res = client.insert('resource-lists', bob2, node_selector, etag=res.etag)
    assert res.code == 201, (res.code, res)

    # insert an element (when there's already one)
    try:
        res = client.insert('resource-lists', bob2, node_selector)
        assert False, `res`
    except AlreadyExists:
        pass

    # replace an element, check etag by the way, it should be equal to that of last result
    res = client.put('resource-lists', bob1, node_selector, etag=res.etag)
    assert res.code == 200, (res.code, res)

    # delete an element
    res = client.delete('resource-lists', node_selector, etag=res.etag)
    assert res.code == 200, (res.code, res)

    # common http errors:
    try:
        res = client.delete('resource-lists', node_selector)
        assert res.code == 200, (res.code, res)
    except HTTPError, e:
        if e.code != 404:
            raise

    # connection errors:
    client2 = XCAPClient('http://www.fdsdfgh.com:32452', user)
    try:
        client2.get('resource-lists')
        assert False, 'should not get there'
    except URLError:
        pass

    # https and authentication:
    read_xcapclient_cfg()
    client3 = XCAPClient(Account.xcap_root, user, '123', auth='basic')
    watchers = client3.get('watchers')
    assert isinstance(watchers, Document), `watchers`
    assert watchers.content_type == 'application/xml', watchers.content_type

    # conditional GET:
    client.put('resource-lists', document)
    got = client.get('resource-lists')    
    assert got==document, (document, got)
    etag = got.etag
    
    got2 = client.get('resource-lists', etag=etag)
    assert document==got2, (document, got2)

    try:
        got3 = client.get('resource-lists', etag=etag + 'xxx')
        assert False, "should've gotten 412 error instead: %r" % got3
    except HTTPError, e:
        if e.code != 412:
            raise

    # conditional DELETE:
    try:
        res = client.delete('resource-lists', etag=etag+'yyy')
        assert False, "should've gotten 412 error instead: %r" % res
    except HTTPError, e:
        if e.code != 412:
            raise
