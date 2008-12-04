#!/usr/bin/env python

from distutils.core import setup
from xcaplib import __version__

setup(name         = "python-xcaplib",
      version      = __version__,
      author       = "Denis Bilenko",
      author_email = "support@ag-projects.com",
      url          = "http://openxcap.org/",
      description  = "Client for managing full or partial XML documents on XCAP servers (RFC 4825)",
      license      = "LGPL",
      platforms    = ["Platform Independent"],
      classifiers  = [
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Service Providers",
        "License :: OSI Approved :: Lesser General Public License (LGPL)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python",
      ],
      packages = ['xcaplib'],
      scripts  = ['xcapclient'])
