class RequestError(Exception):
    pass

class HTTPError(RequestError):

    def __init__(self, response):
        self.response = response

    def __getattr__(self, item):
        return getattr(self.response, item)

    def __str__(self):
        return str(self.response)

# XXX subclass HTTPError for all useful error responses - 404, 401, 400, 409
# XXX subclass 409 for xcap errors like in xcap.errors

class AlreadyExists(RequestError):
    """Raised when trying to insert a document or node to a non-free location

    Depending on presence of node parameter an appropriate subclass is returned:

    >>> raise AlreadyExists('resource-lists')
    Traceback (most recent call last):
     ...
    DocumentAlreadyExists: Document 'resource-lists' already exists

    >>> raise AlreadyExists('resource-lists', '/resource-lists/list')
    Traceback (most recent call last):
     ...
    NodeAlreadyExists: Node '/resource-lists/list' already exists in 'resource-lists'
    """
    def __new__(cls, application, node=None):
        if node is None:
            return RequestError.__new__(DocumentAlreadyExists, application, node)
        else:
            return RequestError.__new__(NodeAlreadyExists, application)

    def __init__(self, application, node=None):
        self.application = application
        self.node = node

class DocumentAlreadyExists(AlreadyExists):
    def __str__(self):
        return 'Document %r already exists' % self.application

class NodeAlreadyExists(AlreadyExists):
    def __str__(self):
        return 'Node %r already exists in %r' % (self.node, self.application)

if __name__=='__main__':
    import doctest
    doctest.testmod()

