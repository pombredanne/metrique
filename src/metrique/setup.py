#!/usr/bin/python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
# Author: "Chris Ward <cward@redhat.com>

import logging
from setuptools import setup

logging.basicConfig(format='')
logger = logging.getLogger('metrique')

__pkg__ = 'metrique'
__version__ = '0.2.2'
__release__ = "6a"
__nvr__ = '%s-%s' % (__version__, __release__)
__pkgs__ = ['metrique']
__provides__ = ['metrique']
__desc__ = 'Metrique - Client Libraries'
__scripts__ = [
    'bin/metrique-setup',
]
__requires__ = [
    'metriqueu (>=%s)' % __version__,
    'pandas (>=0.12)',
    'requests (==1.2.3)',
    'tornado (>=3.0)',
]
__irequires__ = [
    'metriqueu>=%s' % __version__,
    'pandas>=0.12',
    'requests==1.2.3',
    'tornado>=3.0',
]
pip_src = 'https://pypi.python.org/packages/source'
__deplinks__ = []

with open('README.rst') as _file:
    readme = _file.read()

github = 'https://github.com/drpoovilleorg/metrique'
download_url = '%s/archive/master.zip' % github

default_setup = dict(
    url=github,
    license='GPLv3',
    author='Chris Ward',
    author_email='cward@redhat.com',
    download_url=download_url,
    long_description=readme,
    data_files=[],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Natural Language :: English',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 2 :: Only',
        'Topic :: Database',
        'Topic :: Office/Business',
        'Topic :: Scientific/Engineering',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
        'Topic :: Scientific/Engineering :: Visualization',
        'Topic :: Utilities',
    ],
    keywords=['data', 'mining', 'information', 'mongo',
              'etl', 'analysis', 'search', 'query'],
    dependency_links=__deplinks__,
    description=__desc__,
    install_requires=__irequires__,
    name=__pkg__,
    packages=__pkgs__,
    provides=__provides__,
    requires=__requires__,
    scripts=__scripts__,
    version=__nvr__,
)

setup(**default_setup)
