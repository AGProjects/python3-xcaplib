#!/usr/bin/python2

from distutils.core import setup
from xcaplib import __version__

setup(
    name='python-xcaplib',
    version=__version__,

    description='Client for managing full or partial XML documents on XCAP servers (RFC 4825)',
    license='LGPL',
    url='http://openxcap.org/',

    author='AG Projects',
    author_email='support@ag-projects.com',

    platforms=['Platform Independent'],
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Service Providers',
        'License :: OSI Approved :: Lesser General Public License (LGPL)',
        'Operating System :: POSIX :: Linux',
        'Programming Language :: Python',
    ],

    packages=['xcaplib'],
    scripts=['xcapclient']
)
