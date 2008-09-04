#!/usr/bin/env python

from distutils.core import setup
from xcaplib import __version__

setup(name         = "xcaplib",
      version      = __version__,
      author       = "Denis Bilenko",
      author_email = "support@ag-projects.com",
      url          = "http://openxcap.org/",
      description  = "An open source XCAP client library and command-line tool.",
      license      = "BSD",
      platforms    = ["Platform Independent"],
      classifiers  = [
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Service Providers",
        "License :: OSI Approved :: GNU General Public License (GPL)",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python",
      ],
      packages = ['xcaplib'],
      scripts  = ['xcapclient'])
