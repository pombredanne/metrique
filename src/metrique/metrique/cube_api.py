#!/usr/bin/env python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
# Author: "Chris Ward" <cward@redhat.com>

'''
This module contains all the Cube related api
functionality.

Create/Drop/Update cubes.
Save/Remove cube objects.
Create/Drop cube indexes.
'''

from copy import deepcopy
from datetime import datetime
import logging
logger = logging.getLogger(__name__)

from metrique.utils import api_owner_cube
from metriqueu.utils import batch_gen, set_default, ts2dt, dt2ts, utcnow


def list_all(self, startswith=None):
    ''' List all valid cubes for a given metrique instance '''
    return sorted(self._get(startswith))


@api_owner_cube('')
def sample_fields(self, sample_size=None, query=None, **kwargs):
    '''
    List all valid fields for a given cube

    :param list exclude_fields:
        List (or csv) of fields to exclude from the results
    :param bool mtime:
        Include mtime details
    '''
    result = self._get(kwargs.get('cmd'), sample_size=sample_size,
                       query=query)
    return sorted(result)


@api_owner_cube
def stats(self, **kwargs):
    return self._get(kwargs.get('cmd'))


### ADMIN ####

@api_owner_cube
def drop(self, force=False, **kwargs):
    '''
    Drops current cube from timeline

    :param bool force: really, do it!
    '''
    if not force:
        raise ValueError(
            "DANGEROUS: set false=True to drop %s.%s" % (
                kwargs.get('owner'), kwargs.get('cube')))
    return self._delete(kwargs.get('cmd'))


@api_owner_cube
def register(self, **kwargs):
    '''
    Drops current cube from timeline

    '''
    return self._post(kwargs.get('cmd'))


@api_owner_cube
def update_role(self, username, action='push', role='read', **kwargs):
    '''
    Add/Remove cube ACLs

    :param string action: action to take (push, pull)
    :param string role:
        Permission: read, write, admin)
    '''
    return self._post(kwargs.get('cmd'),
                      username=username, action=action, role=role)


######### INDEX #########

@api_owner_cube('index')
def list_index(self, **kwargs):
    '''
    List indexes for either timeline or warehouse.

    '''
    result = self._get(kwargs.get('cmd'))
    return sorted(result)


@api_owner_cube('index')
def ensure_index(self, key_or_list, **kwargs):
    '''
    Ensures that an index exists on this cube.

    :param string/list key_or_list:
        Either a single key or a list of (key, direction) pairs.
    '''
    return self._post(kwargs.get('cmd'), ensure=key_or_list)


@api_owner_cube('index')
def drop_index(self, index_or_name, **kwargs):
    '''
    Drops the specified index on this cube.

    :param string/list index_or_name:
        index (or name of index) to drop
    '''
    return self._delete(kwargs.get('cmd'), drop=index_or_name)


######## SAVE/REMOVE ########

@api_owner_cube
def save(self, objects, batch_size=None, **kwargs):
    '''
    Save a list of objects the given metrique.cube.
    Returns back a list of object ids (_id|_oid) saved.

    :param list objects: list of dictionary-like objects to be stored
    :param int batch_size: maximum slice of objects to post at a time
    :rtype: list - list of object ids saved
    '''
    batch_size = set_default(batch_size, self.config.batch_size)

    olen = len(objects) if objects else None
    if not olen:
        self.logger.debug("... No objects to save")
        return []

    # get 'now' utc timezone aware datetime object
    now = utcnow(tz_aware=True)

    if (batch_size <= 0) or (olen <= batch_size):
        saved = self._post(kwargs.get('cmd'), objects=objects, mtime=now)
    else:
        saved = []
        k = 0
        for batch in batch_gen(objects, batch_size):
            _saved = self._post(kwargs.get('cmd'), objects=batch, mtime=now)
            saved.extend(_saved)
            k += batch_size
            self.logger.info("... %i of %i" % (k, olen))
    self.logger.info("... Saved %s NEW docs" % len(saved))
    return sorted(saved)


@api_owner_cube
def remove(self, ids, backup=False, **kwargs):
    '''
    Remove objects from cube timeline

    :param list ids: list of object ids to remove
    :param bool backup: return the documents removed to client?
    '''
    if not ids:
        raise RuntimeError("empty id list")
    else:
        result = self._delete(kwargs.get('cmd'), ids=ids, backup=backup)
    return sorted(result)


def _activity_backwards(val, removed, added):
    if isinstance(added, list) and isinstance(removed, list):
        val = [] if val is None else val
        inconsistent = False
        for ad in added:
            if ad in val:
                val.remove(ad)
            else:
                inconsistent = True
        val.extend(removed)
    else:
        inconsistent = val != added
        val = removed
    return val, inconsistent


def _activity_import_doc(cube, time_doc, activities):
    '''
    Import activities for a single document into timeline.
    '''
    batch_updates = [time_doc]
    # We want to consider only activities that happend before time_doc
    # do not move this, because time_doc._start changes
    # time_doc['_start'] is a timestamp, whereas act[0] is a datetime
    td_start = ts2dt(time_doc['_start'])
    activities = filter(lambda act: (act[0] < td_start and
                                     act[1] in time_doc), activities)
    for when, field, removed, added in activities:
        removed = dt2ts(removed) if isinstance(removed, datetime) else removed
        added = dt2ts(added) if isinstance(added, datetime) else added
        last_doc = batch_updates.pop()
        # check if this activity happened at the same time as the last one,
        # if it did then we need to group them together
        if last_doc['_end'] == when:
            new_doc = last_doc
            last_doc = batch_updates.pop()
        else:
            try:
                # set start to creation time if available
                creation_field = cube.get_property('cfield')
                start = last_doc[creation_field]
            except:
                start = when
            new_doc = deepcopy(last_doc)
            new_doc.pop('_id') if '_id' in new_doc else None
            new_doc['_start'] = start
            new_doc['_end'] = when
            last_doc['_start'] = when
        last_val = last_doc[field]
        new_val, inconsistent = _activity_backwards(new_doc[field],
                                                    removed, added)
        new_doc[field] = new_val
        # Check if the object has the correct field value.
        if inconsistent:
            msg = 'Inconsistency: %s %s: %s -> %s, object has %s' % (
                last_doc['_oid'], field, removed, added, last_val)
            logger.debug(msg)
            msg = '        Types: %s -> %s, object has %s.' % (
                type(removed), type(added), type(last_val))
            logger.debug(msg)
            if '_corrupted' not in new_doc:
                new_doc['_corrupted'] = {}
            new_doc['_corrupted'][field] = added
        # Add the objects to the batch
        batch_updates.append(last_doc)
        batch_updates.append(new_doc)
    return batch_updates


# FIXME: make sure the query being sent (in all cases...) hits BASE_INDEX
def _get_time_docs_cursor(cube, ids):
    if isinstance(ids, list):
        q = '_oid in %s' % ids
    if isinstance(ids, tuple):
        q = '_oid >= %s and _oid <= %s' % ids
    time_docs = cube.find(q, fields='__all__', date='~',
                          sort=[('_oid', 1), ('_start', 1)], raw=True)
    return time_docs


def _activity_import(cube, ids, batch_size):
    time_docs = _get_time_docs_cursor(cube, ids)

    # generator that yields by ids ascending
    # has format: (id, [(when, field, removed, added)])
    act_generator = cube.activity_get(ids)

    last_doc_id = -1
    aid = -1
    batched_updates = []
    for time_doc in time_docs:
        _oid = time_doc['_oid']
        # we want to update only the oldest version of the object
        while aid < _oid:
            aid, acts = act_generator.next()
        if _oid != last_doc_id and aid == _oid:
            last_doc_id = _oid
            updates = _activity_import_doc(cube, time_doc, acts)
            if len(updates) > 1:
                batched_updates += updates
        if len(batched_updates) >= batch_size:
            cube.save_objects(batched_updates)
            batched_updates = []
    if batched_updates:
        cube.save_objects(batched_updates)


def activity_import(self, ids=None, save_batch_size=1000, chunk_size=1000):
    '''
    Run the activity import for a given cube, if the
    cube supports it.

    Essentially, recreate object histories from
    a cubes 'activity history' table row data,
    and dump those pre-calcultated historical
    state object copies into the timeline.

    :param object ids:
        - None: import for all ids
        - list of ids: import for ids in the list
        - csv list of ids:  import for ids in the csv list
        - 2-tuple of ids: import for the ids in the interval
          specified by the tuple
    :param int save_batch_size:
        Determines the size of the batch when sending objects to save to the
        Metrique server
    :param int chunk_size:
        Size of the chunks into which the ids are split, activity import is
        done and saved separately for each batch
    '''
    if ids is None:
        max_oid = self.find('_oid == exists(True)', date='~',
                            sort=[('_oid', -1)], one=True, raw=True)['_oid']
        ids = (0, max_oid)
    if isinstance(ids, tuple):
        for i in range(ids[0], ids[1] + 1, chunk_size):
            _activity_import(self, (i, min(ids[1], i + chunk_size - 1)),
                             batch_size=save_batch_size)
    else:
        if not isinstance(ids, list):
            raise ValueError(
                "Expected ids to be None, tuple or list. Got %s" % type(list))

        for i in range(0, len(ids), chunk_size):
            _activity_import(self, ids[i:i + chunk_size],
                             batch_size=save_batch_size)
