#!/usr/bin/env python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
# Author: "Chris Ward" <cward@redhat.com>

from copy import copy
from datetime import datetime
import os
import pytz
import simplejson as json

testroot = os.path.dirname(os.path.abspath(__file__))
cubes = os.path.join(testroot, 'cubes')


def test_csv2list():
    ' args: csv, delimiter=",") '
    ' always expect output of a list of sorted strings '
    from metrique.utils import csv2list

    d = ','

    l = ['1', '2', '3']
    t = ('1', '2', '3')
    s = set(['1', '2', '3'])
    _s = '1,2,      3'
    _s_semi = '   1; \t  2;   3    '

    assert csv2list(l, d) == l
    assert csv2list(t, d) == l
    assert csv2list(s, d) == l

    assert csv2list(_s, d) == l

    d = ';'
    assert csv2list(_s_semi, d) == l

    assert csv2list(None, d) == []

    try:
        csv2list(True, d)
    except TypeError:
        pass


def test_cube_pkg_mod_cls():
    ''' ie, group_cube -> from group.cube import CubeClass '''
    from metrique.utils import cube_pkg_mod_cls

    pkg, mod, _cls = 'testcube', 'csvfile', 'Csvfile'
    cube = 'testcube_csvfile'
    assert cube_pkg_mod_cls(cube) == (pkg, mod, _cls)


def test_get_cube():
    ' args: cube, path '
    from metrique.utils import get_cube

    # expected to be available (built-ins)
    get_cube('csvdata_rows')
    get_cube('jsondata_objs')
    get_cube('sqldata_generic')
    get_cube('sqldata_teiid')

    # test pulling from arbitrary path/pkg
    paths = [os.path.dirname(os.path.abspath(__file__))]
    cube = 'csvcube_local'
    pkgs = ['testcubes']
    get_cube(cube=cube, pkgs=pkgs, cube_paths=paths)


# FIXME: THIS IS REALLY SLOW... reenable by adding test_ prefix
def get_timezone_converter():
    ' args: from_timezone '
    ' convert is always TO utc '
    from metrique.utils import get_timezone_converter

    # note: caching timezones always takes a few seconds
    good = 'US/Eastern'
    good_tz = pytz.timezone(good)

    now_utc = datetime.now(pytz.utc)

    now_est = copy(now_utc)
    now_est = now_est.astimezone(good_tz)
    now_est = now_est.replace(tzinfo=None)

    c = get_timezone_converter(good)
    assert c(None, now_est) == now_utc


def test_json_encode():
    ' args: obj '
    from metrique.utils import json_encode

    now = datetime.utcnow()

    dct = {"a": now}

    _dct = json.loads(json.dumps(dct, default=json_encode))
    assert isinstance(_dct["a"], float)
