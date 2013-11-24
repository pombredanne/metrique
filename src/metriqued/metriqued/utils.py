#!/usr/bin/env python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
# Author: "Chris Ward <cward@redhat.com>

from bson.son import SON
import os
import pql
import re
from hashlib import sha1

from metriqueu.utils import batch_gen, dt2ts

OBJECTS_MAX_BYTES = 16777216
EXISTS_SPEC = {'$exists': 1}


def date_pql_string(date):
    if date is None:
        return '_end == None'
    if date == '~':
        return ''

    before = lambda d: '_start <= %f' % dt2ts(d)
    after = lambda d: '(_end >= %f or _end == None)' % dt2ts(d)
    split = date.split('~')
    # replace all occurances of 'T' with ' '
    # this is used for when datetime is passed in
    # like YYYY-MM-DDTHH:MM:SS instead of
    #      YYYY-MM-DD HH:MM:SS as expected
    # and drop all occurances of 'timezone' like substring
    split = [re.sub('\+\d\d:\d\d', '', d.replace('T', ' ')) for d in split]
    if len(split) == 1:
        # 'dt'
        return '%s and %s' % (before(split[0]), after(split[0]))
    elif split[0] == '':
        # '~dt'
        return before(split[1])
    elif split[1] == '':
        # 'dt~'
        return after(split[0])
    else:
        # 'dt~dt'
        return '%s and %s' % (before(split[1]), after(split[0]))


def query_add_date(query, date):
    date_pql = date_pql_string(date)
    if query and date_pql:
        return '%s and %s' % (query, date_pql)
    return query or date_pql


def get_pids(pid_dir):
    pid_dir = os.path.expanduser(pid_dir)
    # eg, server.pid.22325, server.pid.23526
    pids = []
    for f in os.listdir(pid_dir):
        pid_re = re.search(r'metriqued.(\d+).pid', f)
        if pid_re:
            pids.append(pid_re.groups()[0])
    pids = clear_stale_pids(pids, pid_dir)
    return map(int, pids)


def clear_stale_pids(pids, pid_dir):
    'check for and remove any pids which have no corresponding process'
    procs = os.listdir('/proc')
    running = [pid for pid in pids if pid in procs]
    for pid in pids:
        if pid not in running:
            pid_file = 'metriqued.%s.pid' % pid
            path = os.path.join(pid_dir, pid_file)
            os.remove(path)
    return running


def insert_bulk(_cube, docs, size=-1):
    # little reason to batch insert...
    # http://stackoverflow.com/questions/16753366
    # and after testing, it seems splitting things
    # up more slows things down.
    if size <= 0:
        _cube.insert(docs, manipulate=False)
    else:
        for batch in batch_gen(docs, size):
            _cube.insert(batch, manipulate=False)


def jsonhash(obj, root=True):
    '''
    calculate the objects hash based on all field values
    '''
    if isinstance(obj, dict):
        result = frozenset(
            (k, jsonhash(v, False)) for k, v in obj.items())
    elif isinstance(obj, list):
        result = tuple(jsonhash(e, False) for e in obj)
    else:
        result = obj
    return sha1(repr(result)).hexdigest() if root else result


def make_index_spec(_start=EXISTS_SPEC, _end=EXISTS_SPEC,
                    _oid=EXISTS_SPEC, _hash=EXISTS_SPEC):
    spec = SON([('_start', _start),
                ('_end', _end),
                ('_oid', _oid),
                ('_hash', _hash)])
    return spec


def parse_pql_query(query):
    if not query:
        return {}
    if not isinstance(query, basestring):
        raise TypeError("query expected as a string")
    pql_parser = pql.SchemaFreeParser()
    spec = pql_parser.parse(query)
    return spec


def parse_oids(oids, delimeter=','):
    if isinstance(oids, basestring):
        oids = [s.strip() for s in oids.split(delimeter)]
    if type(oids) is not list:
        raise TypeError("ids expected to be a list")
    return oids


def set_property(dct, key, value, _types):
    # expecting iterable
    assert isinstance(_types, (list, tuple))
    if value is None:
        return dct
    elif not isinstance(value, tuple(_types)):
        # isinstance expects arg 2 as tuple
        raise TypeError(
            "Invalid type for %s; "
            "got (%s), expected %s" % (key, type(value), _types))
    else:
        dct[key] = value
    return dct
