#!/usr/bin/env python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
# Author: "Chris Ward <cward@redhat.com>

import os

from metrique.utils import get_cube
csvdata_rows = get_cube('csvdata_rows')

cwd = os.path.dirname(os.path.abspath(__file__))
tests_root = '/'.join(cwd.split('/')[0:-2])
fixtures = os.path.join(tests_root, 'fixtures')
DEFAULT_URI = os.path.join(fixtures, 'us-idx-eod.csv')
DEFAULT_ID = 'symbol'


class Csvfile(csvdata_rows):
    """
    Test Cube; csv based
    """
    name = 'testcube_csvfile'

    def extract(self, uri=DEFAULT_URI, _oid=DEFAULT_ID, **kwargs):
        return super(Csvfile, self).extract(uri=uri, _oid=_oid, **kwargs)

if __name__ == '__main__':
    from metriquec.argparsers import cube_cli
    cube_cli(Csvfile)
