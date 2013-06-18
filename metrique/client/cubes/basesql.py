#!/usr/bin/env python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
# Author: "Chris Ward <cward@redhat.com>

import logging
logger = logging.getLogger(__name__)

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from datetime import time as dt_time
import re
import time

from metrique.client.cubes.basecube import BaseCube

from metrique.tools.constants import UTC
from metrique.tools.constants import INT_TYPE, FLOAT_TYPE

DEFAULT_ROW_LIMIT = 100000
MAX_WORKERS = 2


class BaseSql(BaseCube):
    '''
    '''
    def __init__(self, host, port, db, row_limit=0, **kwargs):
        self.host = host
        self.port = port
        self.db = db
        self.row_limit = self.setdefault(row_limit, DEFAULT_ROW_LIMIT)
        super(BaseSql, self).__init__(**kwargs)

    @property
    def proxy(self):
        raise NotImplementedError("BaseSql has not defined a proxy")

    def _sql_fetchall(self, sql, start, field, row_limit):
        '''
        '''
        logger.debug('Fetching rows')

        # return the raw as token if no convert is defined by driver (self)
        convert = self.get_property('convert', field, None)

        rows = list(self.proxy.fetchall(sql, row_limit, start))
        k = len(rows)

        logger.debug('... fetched (%i)' % len(rows))
        if not rows:
            return []

        logger.debug('Preparing row data...')
        t0 = time.time()
        _rows = []

        for row in rows:
            _rows.append(self._get_row(row, field, convert))

        t1 = time.time()
        logger.info('... Rows prepared %i docs (%i/sec)' % (
            k, float(k) / (t1 - t0)))
        return _rows

    def _get_row(self, row, field, convert):
        id = row[0]  # id 'column' is expected first
        raw = row[1]  # and raw token 'lookup' second
        if type(raw) is date:
            # force convert dates into datetimes... otherwise mongo barfs
            raw = datetime.combine(raw, dt_time()).replace(tzinfo=UTC)
        # convert based on driver defined conversion method
        # and cast to appropriate data type
        if convert:
            tokens = convert(self, raw)
        else:
            tokens = raw

        return {'id': id, 'field': field, 'tokens': tokens}

    def grouper(self, rows):
        ''' Group tokens by id/field '''
        k = len(rows)
        logger.debug('... ... ... Grouping started of %s rows!' % k)
        grouped = {}
        t0 = time.time()
        for row in rows:
            id = row['id']
            field = row['field']
            tokens = row['tokens']
            grouped.setdefault(id, {})
            grouped[id].setdefault(field, [])
            if not tokens:  # if tokens is empty, don't update the list
                continue
            grouped[id][field].append(tokens)
        t1 = time.time()
        logger.info('... ... ... Grouped %i docs (%i/sec)' % (
            k, float(k) / (t1 - t0)))
        return grouped

    def extract(self, force=False, id_delta=None,
                workers=MAX_WORKERS, fields='__all__'):
        saved = 0
        fields = self.parse_fields(fields)
        if self.config.async:
            with ThreadPoolExecutor(workers) as executor:
                fmap = []
                future_builds = []
                for field in fields:
                    fmap.append(field)
                    future_builds.append(executor.submit(
                        self._extract, field, force, id_delta))
                for k, future in enumerate(as_completed(future_builds)):
                    field = fmap[k]
                    try:
                        objects = future.result()
                    except Exception as e:
                        logger.error("ERROR (%s): %s" % (field, e))
                    else:
                        saved += self.save_objects(objects, update=True)
        else:
            for field in self.fields:
                if fields and field not in fields:
                    continue
                objects = self._extract(field, force, id_delta)
                saved += self.save_objects(objects, update=True)

    def _extract(self, field, force=False, id_delta=None):
        '''
        SQL import method
        '''
        if id_delta:
            if force:
                raise RuntimeError(
                    "force and id_delta can't be used simultaneously")

        db = self.get_property('db', field)
        table = self.get_property('table', field)
        db_table = '%s.%s' % (db, table)
        column = self.get_property('column', field)
        table_column = '%s.%s' % (table, column)

        # max number of rows to return per call (ie, LIMIT)
        row_limit = self.get_property('row_limit', field, self.row_limit)
        if not row_limit:
            row_limit = DEFAULT_ROW_LIMIT
        try:
            row_limit = int(row_limit)
        except (TypeError, ValueError):
            raise ValueError(
                "row_limit must be a number. Got (%s)" % row_limit)

        sql_where = []
        sql_groupby = ''
        _sql = self.get_property('sql', field)
        if isinstance(_sql, basestring):
            _sql = [_sql]
        if not _sql:
            sql = 'SELECT %s, %s.%s FROM %s' % (
                table_column, table, field, db_table)
        else:
            sql = 'SELECT %s, %s FROM ' % (table_column, _sql[0])
            _from = [db_table]

            # FIXME: THIS IS UGLY! use a dict... or sqlalchemy
            if _sql[1]:
                _from.extend(_sql[1])
            sql += ', '.join(_from)
            sql += ' '

            try:
                if _sql[2]:
                    sql += ' '.join(_sql[2])
            except IndexError:
                pass
            sql += ' '

            try:
                if _sql[3]:
                    sql_where.append('(%s)' % ' OR '.join(_sql[3]))
            except IndexError:
                pass

            try:
                if _sql[4]:
                    sql_groupby = _sql[4]
            except IndexError:
                pass

        delta_filter = []
        delta_filter_sql = None

        # force full update
        if force:
            _delta = False
        else:
            _delta = self.get_property('delta', field, True)

        if _delta:
            # delta is enabled
            # the following deltas are mutually exclusive
            if id_delta:
                delta_sql = "(%s IN (%s))" % (table_column, id_delta)
                delta_filter.append(delta_sql)
            elif self.get_property('delta_new_ids', field):
                # if we delta_new_ids is on, but there is no 'last_id',
                # then we need to do a FULL run...
                last_id = self.get_last_id(field)
                if last_id:
                    try:
                            last_id = int(last_id)
                    except (TypeError, ValueError):
                            pass

                    if type(last_id) in [INT_TYPE, FLOAT_TYPE]:
                        last_id_sql = "%s > %s" % (table_column, last_id)
                    else:
                        last_id_sql = "%s > '%s'" % (table_column, last_id)
                    delta_filter.append(last_id_sql)

                mtime_columns = self.get_property('delta_mtime', field)
                if mtime_columns:
                    if isinstance(mtime_columns, basestring):
                        mtime_columns = [mtime_columns]
                    last_update_dt = self.last_mtime(field=field)
                    if last_update_dt:
                        last_update_dt = last_update_dt.strftime(
                            '%Y-%m-%d %H:%M:%S %z')
                        dt_format = "yyyy-MM-dd HH:mm:ss z"
                        for _column in mtime_columns:
                            _sql = "%s > parseTimestamp('%s', '%s')" % (
                                _column, last_update_dt, dt_format)
                            delta_filter.append(_sql)

        if delta_filter:
            delta_filter_sql = ' OR '.join(delta_filter)
            sql_where.append('(%s)' % delta_filter_sql)

        if sql_where:
            sql += ' WHERE %s ' % ' AND '.join(sql_where)

        if sql_groupby:
            sql += ' GROUP BY %s ' % sql_groupby

        if self.get_property('sort', field, True):
            sql += " ORDER BY %s ASC" % table_column

        # whether to query for distinct rows only or not; default, no
        if self.get_property('distinct', field, False):
            sql = re.sub('^SELECT', 'SELECT DISTINCT', sql)

        start = 0
        _stop = False
        rows = []

        # FIXME: prefetch the next set of rows while importing to mongo
        logger.debug('... ... Starting SQL fetchall routine!')

        container = self.get_property('container', field)

        objects = []
        while not _stop:
            rows = self._sql_fetchall(sql, start, field, row_limit)
            k = len(rows)
            if k > 0:
                grouped = self.grouper(rows)
                t0 = time.time()
                _id_k = 0
                for _id in grouped.iterkeys():
                    _id_k += 1
                    for field in grouped[_id].iterkeys():
                        tokens = grouped[_id][field]
                        if not tokens:
                            tokens = None
                        elif container and type(tokens) is not list:
                            tokens = [tokens]
                        elif not container and type(tokens) is list:
                            if len(tokens) > 1:
                                raise TypeError(
                                    "Tokens contains too many values (%s); "
                                    "(set container=True?)" % (tokens))
                            else:
                                tokens = tokens[0]
                        objects.append({'_id': _id, field: tokens})
                t1 = time.time()
                logger.info('... ... Processed %i docs (%i/sec)' % (
                    k, k / (t1 - t0)))
            else:
                logger.debug('... ... No rows; nothing to process')

            if k < row_limit:
                _stop = True
            else:
                start += k
                if k != row_limit:  # theoretically, k == row_limit
                    logger.warn(
                        "rows count seems incorrect! "
                        "row_limit: %s, row returned: %s" % (
                            row_limit, k))

        return objects