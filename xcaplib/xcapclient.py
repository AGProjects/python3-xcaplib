#!/usr/bin/env python
"""
  %prog: Client for managing full or partial XML documents on XCAP servers (RFC 4825)
  %prog [OPTIONS] --app AUID ACTION [NODE-SELECTOR]

  ACTION is an operation to perform: get, replace, insert, put or delete.
  Presence of NODE-SELECTOR indicates that action is to be performed on an
  element or an attribute.
"""

import sys

OPT_COMPLETE = '--print-completions'

try:
    import os
    import urllib2
    import optparse
    import traceback
    from StringIO import StringIO
    from twisted.python import log as twistedlog

    # prevent application.configuration from installing its SimpleObserver
    # which prints to stdout all kinds of useless crap from twisted
    twistedlog.defaultObserver = None
    # not using twisted anymore? remove it?

    from application.configuration import ConfigFile, ConfigSection

    try:
        from twisted.python.util import getPassword
    except ImportError:
        getPassword = raw_input

    from xcaplib.client import XCAPClient, Resource, HTTPError, addinfourl, AlreadyExists
    from xcaplib.xpath_completion import *
except:
    if OPT_COMPLETE in sys.argv[-2:]:
        sys.exit(1)
    else:
        raise

CONFIG_FILE = os.path.expanduser('~/.sipclient/config.ini')

# to guess app from /NODE-SELECTOR
app_by_root_tag = {
    #root tag        :  app,
    'resource-lists' : 'resource-lists',
    'rls-services'   : 'rls-services',
    'ruleset'        : 'pres-rules',
    'presence'       : 'pidf-manipulation',
    'watchers'       : 'watchers',
    'xcap-caps'      : 'xcap-caps'}

root_tags = ['/' + root_tag for root_tag in app_by_root_tag.keys()]
del root_tag

update_actions = ['put', 'insert', 'replace']
actions = ['get', 'delete'] + update_actions

logfile = None
#logfile = file('./xcapclient.log', 'a+')

def log(s, *args, **kwargs):
    if logfile:
        s = str(s)
        if args:
            s = s % args
        if kwargs:
            s = s % kwargs
        logfile.write(s + '\n')

class OptionParser_NoExit(optparse.OptionParser):
    "raise ValueError instead of killing the process with error message"
    # no need for error messages in completion
    def error(self, msg):
        raise ValueError(msg)

class User:

    def __init__(self, username, domain=None, password=None):
        self.username = username
        self.domain = domain
        self.password = password

    def __str__(self):
        if self.password is None:
            return '%s@%s' % (self.username, self.domain)
        else:
            return '%s:%s@%s' % (self.username, self.password, self.domain)

    def __repr__(self):
        return '%s(%r, %r, %r)' % (self.__class__.__name__, self.username, self.domain, self.password)

    def without_password(self):
        return '%s@%s' % (self.username, self.domain)


class Auth:

    def __new__(cls, auth):
        if auth.lower() == 'none':
            return None
        else:
            return auth.lower()


class Account(ConfigSection):
    _datatypes = {
        'auth' : Auth,
        'password' : str}
    sip_address = ''
    password = None
    username = ''
    domain = ''
    auth = None
    xcap_root = ''

def get_account_section(account_name=None):
    if account_name is None:
        return "Account"
    else:
        return "Account_%s" % account_name

def read_default_options(account_section='Account'):
    client_config = ConfigFile(CONFIG_FILE)
    client_config.read_settings(account_section, Account)
    if client_config.get_section(account_section) is None:
        return None
    else:
        return dict((k, v) for (k, v) in Account.__dict__.iteritems() if k[:1]!='_' and v)

# parameters of the client; may be used by other clients (e.g. openxcap test system)
def setup_parser_client(parser):

    help = ("The account name from which to read account settings. "
            "Corresponds to section Account_NAME in the configuration file. "
            "If not supplied, the section Account will be read.")
    parser.add_option("-a", "--account-name", type="string", help=help, metavar="NAME")

    parser.add_option("--show-config", action="store_true", default=False,
                      help="show options from the configuration file; use together with --account-name")

    help = 'XCAP root, e.g. https://xcap.example.com/xcap-root'

    parser.add_option("--xcap-root", help=help, default=Account.xcap_root)

    help = "SIP address of the user in the form username@domain"
    parser.add_option("--sip-address", default=Account.sip_address, help=help)

    # the older variant of sip_address: supply username and domain independently
    parser.add_option('--username', default=Account.username, help=optparse.SUPPRESS_HELP)
    parser.add_option('--domain',   default=Account.domain, help=optparse.SUPPRESS_HELP)

    help = 'password to use if authentication is required. If not supplied will be asked interactively'
    parser.add_option('-p', '--password', default=Account.password, help=help)

    help="authentification type, basic, digest or none"
    parser.add_option("--auth", help=optparse.SUPPRESS_HELP)

# parameters of the request to perform, specific to this script
def setup_parser_request(parser):
    help="Application Unique ID. There's no default value; however, it may be " + \
         "guessed from NODE-SELECTOR or from the input file. " + \
         "Known apps: %s" % ', '.join(apps)
    parser.add_option("--app", dest='app', help=help)
    parser.add_option("--filename", dest='filename')

    setup_parser_client(parser)

    help='use "global" document selector (by default enabled only for xcap-caps)'
    parser.add_option('--global', help=help, dest='globaltree', action='store_true', default=False)

    parser.add_option("-i", dest='input_filename',
                      help="source file for the PUT request; default is <stdin>")
    parser.add_option("-o", dest='output_filename',
                      help="output file for the server response (successful or rejected); default is <stdout>")
    #parser.add_option("-d", dest='debug', action='store_true', default=False,
    #                  help="print whole http requests and replies to stderr")


def lxml_tag(tag):
    # for tags like '{namespace}tag'
    if '}' in tag:
        namespace, tag = tag.split('}')
        namespace = namespace[1:]
        return namespace, tag
    return None, tag

def get_app_by_input_root_tag(root_tag):
    return app_by_root_tag.get(lxml_tag(root_tag)[1])

apps = app_by_root_tag.values() + ['test-app']

class NullObserver(twistedlog.DefaultObserver):
    def _emit(self, eventDict):
        if eventDict['isError']:
            if eventDict.has_key('failure'):
                text = eventDict['failure'].getTraceback()
            else:
                text = ' '.join([str(m) for m in eventDict['message']]) + '\n'
            logfile.write(text)
            logfile.flush()
        else:
            text = ' '.join([str(m) for m in eventDict['message']]) + '\n'
            logfile.write(text)
            logfile.flush()

wordbreaks = '"\'><=;|&(:' # $COMP_WORDBREAKS

def bash_quote(s):
    return "'" + s + "'"

def bash_escape(s):
    if s[0]=="'":
        return s # already quoted
    for c in wordbreaks:
        s = s.replace(c, '\\' + c)
    return s

def bash_unquote(s):
    if s and s[0]=="'":
        s = s[1:]
        if s and s[-1]=="'":
            s = s[:-1]
        return s
    for c in wordbreaks:
        s = s.replace('\\' + c, c)
    return s


# result is passed as a parameter, since in this case partial
# result is better than no result at all
def completion(result, argv, comp_cword):

    log("argv: %r", argv)

    if twistedlog.defaultObserver is not None:
        twistedlog.defaultObserver.stop()
        twistedlog.defaultObserver = NullObserver()
        twistedlog.defaultObserver.start()

    if len(argv)==comp_cword:
        current, argv = argv[-1], argv[:-1]
    else:
        current = ''

    argv = [bash_unquote(x) for x in argv]
    current_unq = bash_unquote(current)

    def add(*args):
        for x in args:
            x = bash_escape(str(x))
            if x.startswith(current):
                result.add(x)

    def add_quoted(*args):
        for x in args:
            x = bash_quote(str(x))
            if x.startswith(current):
                result.add(x)

    if current:
        if current[0]=="'":
            add = add_quoted
        else:
            add_quoted = add

    def discard(*args):
        for x in args:
            result.discard(x)

    log('current=%r argv=%r', current, argv)

    def complete_options(parser):
        for option in parser.option_list:
            for opt in option._short_opts + option._long_opts:
                add(opt)
        add(*actions)

    parser = OptionParser_NoExit()
    setup_parser(parser)

    if not argv:
        return complete_options(parser)

    if argv[-1]=='--app':
        return add(*apps)
    elif argv[-1]=='--auth':
        return add('basic', 'digest', 'none')
    elif argv[-1]!='-d' and argv[-1][0]=='-':
        return

    options, args = parser.parse_args(argv)
    options._update_careful(read_default_options(get_account_section(options.account_name)) or {})
    fix_options(options)

    if not args:
        complete_options(parser)
        discard(*argv)
        discard('-h', '--help')
        if options.input_filename is not None:
            discard('-o', 'get', 'delete')
        return

    action, args = args[0], args[1:]
    action = action.lower()

    if args:
        return

    if options.app:
        return add_quoted(*complete_xpath(options, options.app, current_unq, action))
    else:
        try:
            root_tag, rest = current_unq[1:].split('/', 1)
        except ValueError:
            add_quoted(*root_tags)
            for x in root_tags:
                add_quoted(x + '/')
        else:
            # get/delete: GET the document, get all the path
            # put: GET the document, get all the paths
            #      read input document, get all the insertion points
            return add_quoted(*complete_xpath(options, app_by_root_tag[root_tag], current_unq, action))


def run_completion(option, raise_ex=False):
    result = set()
    try:
        if sys.argv[-1]==option:
            completion(result, sys.argv[1:-1], len(sys.argv))
        if sys.argv[-2]==option:
            completion(result, sys.argv[1:-2], int(sys.argv[-1]))
    except:
        if raise_ex:
            raise
        else:
            log(traceback.format_exc())
    finally:
        for x in result:
            log(x)
            print x

def complete_xpath(options, app, selector, action):
    client = make_xcapclient(options)
    result = client.get(app)

    if isinstance(result, Resource):
        function = globals().get('enum_paths_'+action+'_wfile', enum_paths_get)
        if function == enum_paths_get:
            return enum_paths_get(result, selector)
        else:
            return function(result, selector, options.input_filename)
    return []


class IndentedHelpFormatter(optparse.IndentedHelpFormatter):
    def __init__(self):
        optparse.IndentedHelpFormatter.__init__(self, max_help_position=25)

    def format_usage(self, usage):
        return usage


def fix_options(options):
    if options.xcap_root is None:
        sys.exit('Please specify XCAP root with --xcap-root. You can also put the default root in %s.' % CONFIG_FILE)

    if options.sip_address:
        if options.username:
            sys.stderr.write('Ignoring "username" when "sip-address" is present.\n')
        if options.domain:
            sys.stderr.write('Ignoring "domain" when "sip-address" is present.\n')
    else:
        if options.username and options.domain:
            options.sip_address = options.username + '@' + options.domain
        else:
            sys.exit('Please specify --sip-address. You can also put the default sip_address in %s.' % CONFIG_FILE)

    if options.sip_address.lower().startswith('sip:'):
        options.sip_address = options.sip_address[4:]

    options.username, options.domain = options.sip_address.split('@')

def update_options_from_config(options):
    default_options = read_default_options(get_account_section(options.account_name))

    if options.show_config:
        if default_options is None:
            sys.exit('Section [%s] was not found in %s' % (get_account_section(options.account_name), CONFIG_FILE))
        else:
            print "Configuration file: %s" % CONFIG_FILE
            print '[%s]' % get_account_section(options.account_name)
            for x in default_options.iteritems():
                print '%s = %s' % x
            sys.exit(0)

    if default_options is not None:
        options._update_careful(default_options)
    fix_options(options)

def parse_args():
    argv = sys.argv[1:]

    if not argv:
        sys.exit('Type %s -h for help.' % sys.argv[0])

    parser = optparse.OptionParser(usage=__doc__, formatter=IndentedHelpFormatter())
    setup_parser(parser)
    options, args = parser.parse_args(argv)
    update_options_from_config(options)

    if not args:
        sys.exit('Please provide ACTION.')

    action, args = args[0], args[1:]
    action = action.lower()
    if action not in actions:
        sys.exit('ACTION must be either GET or PUT or DELETE.')

    options.input_data = None

    if options.input_filename is not None:
        options.input_data = file(options.input_filename).read()
    elif action in update_actions:
        if interactive():
            sys.stderr.write('Reading PUT body from stdin. Type CTRL-D when done\n')
        options.input_data = sys.stdin.read()

    if options.output_filename is None:
        options.output_file = sys.stdout
    else:
        options.output_file = file(options.output_filename, 'w+')

    node_selector = None

    if args:
        node_selector, args = args[0], args[1:]
        if node_selector[0]!='/':
            sys.exit('node selector must start with slash. try %s' % ('/' + node_selector))
        if not options.app:
            root_tag = node_selector.split('/')[1]
            options.app = app_by_root_tag.get(root_tag)
            if not options.app:
                sys.exit('Please specify --app. Root tag %r gives no clue.' % root_tag)

    if not options.app:
        if options.input_data is not None:
            root_tag = get_xml_info(StringIO(options.input_data))[0]
            if root_tag is None:
                sys.exit('Please specify --app. Cannot extract root tag from document %r.' % \
                         (options.input_filename or '<stdin'))
            options.app = get_app_by_input_root_tag(root_tag)
            if options.app is None:
                sys.exit('Please specify --app. Root tag %r gives in the document %r gives no clue.' % \
                         (root_tag, options.input_filename))
        else:
            sys.exit('Please specify --app or NODE-SELECTOR')

    if args:
        sys.exit("Too many positional arguments.")

    if options.app == 'xcap-caps':
        options.globaltree = True

    return options, action, node_selector

def make_xcapclient(options, XCAPClient=XCAPClient):
    user = User(options.username, options.domain, options.password)
    return XCAPClient(options.xcap_root, user.without_password(),
                      user.password, options.auth)

def write_etag(etag):
    if etag:
        sys.stderr.write('etag: %s\n' % etag)

def write_content_length(length):
    sys.stderr.write('content-length: %s\n' % length)

def write_body(options, data):
    options.output_file.write(data)
    options.output_file.flush()
    if options.output_filename: # i.e. not stdout
        sys.stderr.write('%s bytes saved to %s\n' % (len(data), options.output_filename))
    else:
        if data and data[-1]!='\n':
            sys.stderr.write('\n')

def client_request(client, action, options, node_selector):
    kwargs = {}
    if options.globaltree:
        kwargs['globaltree'] = True
    kwargs['filename'] = options.filename
    try:
        if action in ['get', 'delete']:
            return getattr(client, action)(options.app, node_selector, **kwargs)
        elif action in update_actions:
            return getattr(client, action)(options.app, options.input_data, node_selector, **kwargs)
        else:
            raise ValueError('Unknown action: %r' % action)
    except HTTPError, ex:
        return ex

def interactive():
    return hasattr(sys.stdin, 'isatty') and sys.stdin.isatty()

def main():
    if OPT_COMPLETE in sys.argv[-2:]:
        return run_completion(OPT_COMPLETE)
    elif '--debug-completions' in sys.argv[-2:]:
        return run_completion('--debug-completions', raise_ex=True)

    options, action, node_selector = parse_args()
    client = make_xcapclient(options)
    sys.stderr.write('url: %s\n' % client.get_url(options.app, node_selector,
                                                  globaltree=options.globaltree, filename=options.filename))

    try:
        result = client_request(client, action, options, node_selector)
    except AlreadyExists, ex:
        sys.exit(ex)
    if isinstance(result, addinfourl) and result.code==401 and not options.password and interactive():
        authreq = result.headers.get('www-authenticate')
        if authreq:
            mo = urllib2.AbstractBasicAuthHandler.rx.search(authreq)
            if mo:
                options.auth, realm = mo.groups()
                sys.stderr.write('Server requested authentication, but no password was provided.\n')
                options.password = getPassword('Password (realm=%s): ' % realm)
                client = make_xcapclient(options)
                result = client_request(client, action, options, node_selector)
    if isinstance(result, Resource):
        write_etag(result.etag)
        write_content_length(len(result))
        write_body(options, result)
        assert action == 'get', action
    elif isinstance(result, addinfourl):
        sys.stderr.write('%s %s\n' % (result.code, result.msg))
        data = result.read()
        write_etag(result.headers.get('etag'))
        if data:
            write_content_length(len(data))
            write_body(options, data)
        if result not in [200, 201]:
            sys.exit(1)
    else:
        sys.exit('%s: %s' % (result.__class__.__name__, result))

if __name__ == '__main__':
    main()
