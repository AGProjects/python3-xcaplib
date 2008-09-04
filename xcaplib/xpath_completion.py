import traceback
from lxml import etree
from StringIO import StringIO
from xml.sax.saxutils import quoteattr

__all__ = ['enum_paths_get',
           'enum_paths_replace_wfile',
           'enum_paths_insert_wfile',
           'enum_paths_put_wfile',
           'get_xml_info']

logfile = None
#logfile = file('./xcapclient.log', 'a+')
#logfile = sys.stderr

def log(s, *args, **kwargs):
    if logfile:
        s = str(s)
        if args:
            s = s % args
        if kwargs:
            s = s % kwargs
        logfile.write(s + '\n')

def lxml_tag(tag):
    # for tags like '{namespace}tag'
    if '}' in tag:
        namespace, tag = tag.split('}')
        namespace = namespace[1:]
        return namespace, tag
    return None, tag

def get_xml_info(input_file):
    "return tag and attributes of the root element in xml file"
    try:
        if input_file:
            xml = etree.parse(file(input_file))
            el = xml.getroot()
            tag = lxml_tag(el.tag)[1]
            return tag, el.attrib
    except:
        log(traceback.format_exc())
    return None, {}

def fix_namespace_prefix(selector, prefix = 'default'):
    if not selector:
        return ''
    steps = []
    for step in selector.split('/'):
        if not step or ':' in step[:step.find('[')]:
            steps.append(step)
        else:
            steps.append(prefix + ':' + step)
    return '/'.join(steps)

def path_element((prefix, name)):
    if prefix:
        return prefix + ':' + name
    else:
        return name

def xpath(document, selector_start):
    xml = etree.parse(StringIO(document))
    return xpath_xml(xml, selector_start)

def xpath_xml(xml, selector_start, rec_limit=2):
    rec_limit -= 1
    if rec_limit<0:
        return
    x = selector_start.rfind('/')
    parent, current = selector_start[:x], selector_start[x:]
    namespaces = xml.getroot().nsmap.copy()
    namespaces['default'] = namespaces[None]
    del namespaces[None]

    log('parent=%r current=%r', parent, current)
    
    if not parent:
        return xpath_xml(xml, '/' + lxml_tag(xml.getroot().tag)[1] + '/')
    else:
        log('xpath argument: %s', fix_namespace_prefix(parent))
        elements = xml.xpath(fix_namespace_prefix(parent), namespaces=namespaces)
        log('xpath result: %s', elements)

    assert len(elements)==1, elements

    prefixes = dict((v, k) for (k, v) in xml.getroot().nsmap.iteritems())
    return parent, elements[0], prefixes


def enumerate_paths(document, selector_start):
    log('enumerate_paths(%r, %r)', document[:10], selector_start)

    #rejected = set()
    added = set()

    def add(key):
        added.add(key)
#         if key in rejected:
#             return
#         if key in added:
#             added.discard(key)
#             rejected.add(key)
#         else:
#             added.add(key)
    indices = {}
    star_index = 0

    xpath_result = xpath(document, selector_start)
    if isinstance(xpath_result, basestring):
        parent = ''
        add(('element', xpath_result, None, None, True))
        it = []
    else:
        parent, element, prefixes = xpath_result
        context = etree.iterwalk(element, events=("start", "end"))
        it = iter(context)
        the_element = it.next()
        for (k, v) in the_element[1].attrib.items():
            #add(parent + '/@' + k)
            add(('parent-attr', k))
    
        skip = 0

        paths = []
        has_children = False
    
    for action, elem in it:
        log("%s %s", action, elem)
        if action == 'start':
            skip += 1
            if skip==1:
                has_children = False
                star_index += 1
                paths.append(('*', star_index, None))
                namespace, tag = lxml_tag(elem.tag)
                log('namespace=%r prefixes=%r', namespace, prefixes)
                prefix = prefixes[namespace]
                el = path_element((prefix, tag))
                indices.setdefault(el, 0)
                indices[el]+=1
                paths.append((el, None, None))
                paths.append((el, indices[el], None))
                
                for (k, v) in elem.attrib.items():
                    paths.append((el, None, (k, v)))
            else:
                has_children = True
        elif action == 'end':
            if skip == 1:
                for p in paths:
                    el, position, att_test = p
                    add(('element', el, position, att_test, has_children))
                paths = []
            skip -= 1

    log('indices=%r', indices)

    for x in added:
        log('x=%r', x)

    return parent, added, indices, star_index

def discard_longer(added, indices, star_index):
    "if there's exists both entry and entry[1] and no more entries, discard the latter"
    for (tag, index) in indices.iteritems():
        if index == 1:
            added.discard(('element', tag, 1, None, True))
            added.discard(('element', tag, 1, None, False))

    if star_index == 1:
        added.discard(('element', '*', 1, None, True))
        added.discard(('element', '*', 1, None, False))

def discard_ambigous(added, indices, star_index):
    "if there're entry[1], entry[2], etc, discard entry as ambigous"
    for (tag, index) in indices.iteritems():
        if index > 1:
            added.discard(('element', tag, None, None, True))
            added.discard(('element', tag, None, None, False))

    if star_index > 1:
        added.discard(('element', '*', None, None, True))
        added.discard(('element', '*', None, None, False))


def element2xpath(parent, tag, position, att_test):
    s = parent + '/' + tag
    if position:
        s += '[%s]' % position
    if att_test:
        k, v = att_test
        s += '[@%s=%s]' % (k, quoteattr(v))
    return s


def enum_paths_get(document, selector_start):
    parent, added, indices, star_index = enumerate_paths(document, selector_start)
    discard_longer(added, indices, star_index)
    discard_ambigous(added, indices, star_index)
    
    res = []
    for x in added:
        if x[0]=='parent-attr':
            res.append(parent + '/@' + x[1])
        elif x[0]=='element':
            tag, position, att_test, has_children = x[1:]
            s = element2xpath(parent, tag, position, att_test)
            res.append(s)
            if has_children:
                res.append(s + '/')
        else:
            assert False, x
    return res

def enum_paths_replace(document, selector_start, my_tag, my_attrs):
    if my_tag is None:
        return enum_paths_get(document, selector_start)
    parent, added, indices, star_index = enumerate_paths(document, selector_start)
    discard_longer(added, indices, star_index)
    discard_ambigous(added, indices, star_index)   
    res = []
    for x in added:
        if x[0]=='element':
            tag, position, att_test, has_children = x[1:]
            s = element2xpath(parent, tag, position, att_test)
            if has_children:
                res.append(s + '/')
            if tag == my_tag:
                if not att_test:
                    res.append(s)
                else:
                    k, v = att_test
                    if my_attrs.get(k)==v:
                        res.append(s)
    return res

def enum_paths_replace_wfile(document, selector_start, input_filename):
    return enum_paths_replace(document, selector_start, *get_xml_info(input_filename))

def enum_paths_insert(document, selector_start, my_tag, my_attrs):
    parent, added, indices, star_index = enumerate_paths(document, selector_start)
    discard_longer(added, indices, star_index)
    discard_ambigous(added, indices, star_index)
    parents = []
    res = set()
    max_position = 0
    for x in added:
        if x[0]=='element':
            tag, position, att_test, has_children = x[1:]
            s = element2xpath(parent, tag, position, att_test)
            if has_children:
                parents.append(s + '/')
            if tag == my_tag or my_tag is None:
                max_position = max(max_position, position or 1)
                if not att_test:
                    for (k, v) in my_attrs.items():
                        if res is not None:
                            res.add(element2xpath(parent, tag, position, (k, v)))
                else:
                    k, v = att_test
                    if my_attrs.get(k)==v:
                        # there's already an item with @k==v, remove this attr from my_attrs and restart
                        del my_attrs[k]
                        return enum_paths_insert(document, selector_start, my_tag, my_attrs)
    if res is None:
        return parents
    else:
        if my_tag:
            for (k, v) in my_attrs.items():
                res.add(element2xpath(parent, my_tag, None, (k, v)))
                res.add(element2xpath(parent, my_tag, max_position+1, (k, v)))
        return parents + list(res)

def enum_paths_insert_wfile(document, selector_start, input_filename):
    return enum_paths_insert(document, selector_start, *get_xml_info(input_filename))

def enum_paths_put(document, selector_start, my_tag, my_attrs):
    x1 = enum_paths_replace(document, selector_start, my_tag, my_attrs)
    x2 = enum_paths_insert(document, selector_start, my_tag, my_attrs)
    return x1+x2

def enum_paths_put_wfile(document, selector_start, input_filename):
    return enum_paths_put(document, selector_start, *get_xml_info(input_filename))

class _test:

    source = """<?xml version="1.0" encoding="UTF-8"?>
   <resource-lists xmlns="urn:ietf:params:xml:ns:resource-lists"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <list name="friends">
     <entry uri="sip:bill@example.com">
      <display-name>Bill Doe</display-name>
     </entry>
     <entry-ref ref="ref1"/>
     <list name="close-friends">
      <display-name>Close Friends</display-name>
      <entry uri="sip:joe@example.com">
       <display-name>Joe Smith</display-name>
      </entry>
      <entry uri="sip:nancy@example.com">
       <display-name>Nancy Gross</display-name>
      </entry>
      <external anchor="anchor1">
        <display-name>Marketing</display-name>
       </external>
     </list>
    </list>
   </resource-lists>"""

    def enum_path_get(self, node_selector):
        return sorted(list(enum_paths_get(self.source, node_selector)))

    def enum_path_replace(self, *args):
        return sorted(list(enum_paths_replace(self.source, *args)))

    def enum_path_insert(self, *args):
        return sorted(list(enum_paths_insert(self.source, *args)))

    get_result_1 = sorted([
            '/resource-lists/list/list/*[1]',
            '/resource-lists/list/list/*[2]/',
            '/resource-lists/list/list/*[2]',
            '/resource-lists/list/list/*[3]/',
            '/resource-lists/list/list/*[3]',
            '/resource-lists/list/list/*[4]/',
            '/resource-lists/list/list/*[4]',
            '/resource-lists/list/list/display-name',
            '/resource-lists/list/list/entry[1]/',
            '/resource-lists/list/list/entry[1]',
            '/resource-lists/list/list/entry[2]/',
            '/resource-lists/list/list/entry[2]',
            '/resource-lists/list/list/entry[@uri="sip:joe@example.com"]/',
            '/resource-lists/list/list/entry[@uri="sip:joe@example.com"]',
            '/resource-lists/list/list/entry[@uri="sip:nancy@example.com"]/',
            '/resource-lists/list/list/entry[@uri="sip:nancy@example.com"]',
            '/resource-lists/list/list/external/',
            '/resource-lists/list/list/external',
            '/resource-lists/list/list/external[@anchor="anchor1"]/',
            '/resource-lists/list/list/external[@anchor="anchor1"]',
            '/resource-lists/list/list/@name'])

    def test_get(self):
        result = self.enum_path_get('/resource-lists/list/list/')
        for x, y in zip(result, self.get_result_1):
            assert x == y, (x, y)
        assert result == self.get_result_1, result

        result = self.enum_path_get('/resource-lists/list/e')
        result = [x for x in result if x.startswith('/resource-lists/list/e')]
        expected = sorted([
            '/resource-lists/list/entry/',
            '/resource-lists/list/entry',
            '/resource-lists/list/entry-ref',
            '/resource-lists/list/entry-ref[@ref="ref1"]',
            '/resource-lists/list/entry[@uri="sip:bill@example.com"]/',
            '/resource-lists/list/entry[@uri="sip:bill@example.com"]'])
        assert result == expected, result

    def test_replace(self):
        result = self.enum_path_replace('/resource-lists/list/list/', 'entry', {'uri' : 'sip:nancy@example.com'})
        expected = sorted([
            '/resource-lists/list/list/*[2]/',
            '/resource-lists/list/list/*[3]/',
            '/resource-lists/list/list/*[4]/',
            '/resource-lists/list/list/entry[1]/',
            '/resource-lists/list/list/entry[1]',
            '/resource-lists/list/list/entry[2]/',
            '/resource-lists/list/list/entry[2]',
            '/resource-lists/list/list/entry[@uri="sip:joe@example.com"]/',
            '/resource-lists/list/list/entry[@uri="sip:nancy@example.com"]/',
            '/resource-lists/list/list/entry[@uri="sip:nancy@example.com"]',
            '/resource-lists/list/list/external/',
            '/resource-lists/list/list/external[@anchor="anchor1"]/'])
        for x, y in zip(result, expected):
            assert x == y, (x, y)
        assert result == expected, result

        result = self.enum_path_replace('/resource-lists/list/list/', 'entry', {'uri' : 'sip:jack@example.com'})
        expected = sorted([
            '/resource-lists/list/list/*[2]/',
            '/resource-lists/list/list/*[3]/',
            '/resource-lists/list/list/*[4]/',
            '/resource-lists/list/list/entry[1]/',
            '/resource-lists/list/list/entry[1]',
            '/resource-lists/list/list/entry[2]/',
            '/resource-lists/list/list/entry[2]',
            '/resource-lists/list/list/entry[@uri="sip:joe@example.com"]/',
            '/resource-lists/list/list/entry[@uri="sip:nancy@example.com"]/',
            '/resource-lists/list/list/external/',
            '/resource-lists/list/list/external[@anchor="anchor1"]/'])
        for x, y in zip(result, expected):
            assert x == y, (x, y)
        assert result == expected, result

    def test_insert(self):
        result = self.enum_path_insert('/resource-lists/list/list/', 'entry', {'uri' : 'sip:nancy@example.com'})
        # there's already nancy here!
        expected = sorted([
            '/resource-lists/list/list/*[2]/',
            '/resource-lists/list/list/*[3]/',
            '/resource-lists/list/list/*[4]/',
            '/resource-lists/list/list/entry[1]/',
            '/resource-lists/list/list/entry[2]/',
            '/resource-lists/list/list/entry[@uri="sip:joe@example.com"]/',
            '/resource-lists/list/list/entry[@uri="sip:nancy@example.com"]/',
            '/resource-lists/list/list/external/',
            '/resource-lists/list/list/external[@anchor="anchor1"]/'])
        assert result==expected, result

        result = self.enum_path_insert('/resource-lists/list/list/', 'entry', {'uri' : 'sip:jack@example.com'})
        expected = sorted([
            '/resource-lists/list/list/*[2]/',
            '/resource-lists/list/list/*[3]/',
            '/resource-lists/list/list/*[4]/',
            '/resource-lists/list/list/entry[1]/',
            #'/resource-lists/list/list/entry[1]', -- possible, but not recommended
            '/resource-lists/list/list/entry[1][@uri="sip:jack@example.com"]',
            '/resource-lists/list/list/entry[2]/',
            #'/resource-lists/list/list/entry[2]', -- possible, but not recommended            
            '/resource-lists/list/list/entry[2][@uri="sip:jack@example.com"]',
            '/resource-lists/list/list/entry[@uri="sip:joe@example.com"]/',
            '/resource-lists/list/list/entry[@uri="sip:nancy@example.com"]/',
            '/resource-lists/list/list/external/',
            '/resource-lists/list/list/external[@anchor="anchor1"]/',
            '/resource-lists/list/list/entry[@uri="sip:jack@example.com"]',
            #'/resource-lists/list/list/entry[3]', -- possible, but not recommended            
            '/resource-lists/list/list/entry[3][@uri="sip:jack@example.com"]'])
        for x, y in zip(result, expected):
            assert x == y, (x, y)
        assert result==expected, result
        

if __name__ == '__main__':
    t = _test()
    t.test_get()
    t.test_replace()
    t.test_insert()
