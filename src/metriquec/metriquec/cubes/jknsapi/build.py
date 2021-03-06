#!/usr/bin/env python
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
# Author: "Chris Ward <cward@redhat.com>

'''
metriquec.cubes.jknsapi.build
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This module contains the generic metrique cube used
for exctacting build / test run data from Jenkins.
'''

try:
    from concurrent.futures import ThreadPoolExecutor, as_completed
except ImportError:
    from futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from dateutil.parser import parse as dt_parse
from functools import partial
import logging
import requests
import re
import simplejson as json

from metrique import pyclient
from metriqueu.utils import dt2ts

logger = logging.getLogger(__name__)

MAX_WORKERS = 25
SSL_VERIFY = True
# MOVE ALL this to metrique.config; as they're generic and used
# in several other cubes too

rget = partial(requests.get, verify=SSL_VERIFY)

# FIXME: add a version check; this supports jkns 1.529; but doesn't 1.480
# FIXME: subclass jsondata_objs cube?


def obj_hook(dct):
    '''
    JSON decoder.

    Converts the following:
        * 'timestamp' from epoch milliseconds to epoch seconds
        * 'date' strings to epoch seconds
    '''
    _dct = {}
    for k, v in dct.items():
        _k = str(k).replace('.', '_')
        if k == 'timestamp':
            try:
                # convert milliseconds to seconds
                v = v / 1000. if v else v
            except:
                # some cases timestamp is a datetime str
                v = dt2ts(v)
        if k == 'date':
            v = dt2ts(v)
        _dct[_k] = v
    return _dct


def id_when(id):
    '''
    Convert akwards datetime strings to ISO format.
    '''
    if isinstance(id, datetime):
        return id
    else:
        when = re.sub(
            '[_ T](\d\d)[:-](\d\d)[:-](\d\d)$',
            'T\g<1>:\g<2>:\g<3>', id)
        return dt_parse(when)


class Build(pyclient):
    """
    Object used for communication with Jenkins Build (job detail) interface.
    """
    name = 'jknsapi_build'

    def get_objects(self, uri, api_path='api/json', force=False, **kwargs):
        '''
        Query the Jenkins API and generate build /test run detail objects.

        By default, requests are executed across many worker threads to
        speed up extraction, since most of the processing time is consumed
        waiting for response from jenkins.

        :param uri: uri (file://, http(s)://) of csv file to load
        :param api_path: relative uri path for rest api
        :param force: flag for forcing full import; ie, no deltas

        Object properties generated are as follows:
            * _oid: '%s #%s' % (job_name, build_number)
            * job_uri
            * job name
            * job number
            * test report uri
            * test report (see jenkins API docs for specifics)
        '''
        self.api_path = api_path
        args = 'tree=jobs[name,builds[number]]'
        _uri_jobs = '%s/%s?%s' % (uri, self.api_path, args)
        logger.info("Getting Jenkins Job details (%s)" % _uri_jobs)
        # get all known jobs
        content = rget(_uri_jobs).content
        content = json.loads(content, strict=False)
        jobs = content['jobs']
        logger.info("... %i jobs found." % len(jobs))

        if self.config.max_workers > 1:
            objects = self._extract_async(uri, jobs, force)
        else:
            objects = self._extract(uri, jobs, force)
        objects = self.normalize(objects)
        return objects

    def _extract(self, uri, jobs):
        for k, job in enumerate(jobs, 1):
            job_name = job['name']
            logger.debug(
                '%s: %s of %s with %s builds' % (job_name, k,
                                                 len(jobs),
                                                 len(job['builds'])))
            nums = [b['number'] for b in job['builds']]
            builds = [self._get_build(uri, job_name, n) for n in nums]
        return builds

    def _extract_async(self, uri, jobs, force):
        with ThreadPoolExecutor(self.config.max_workers) as executor:
            builds = []
            for k, job in enumerate(jobs, 1):
                job_name = job['name']
                logger.debug(
                    '%s: %s of %s with %s builds' % (job_name, k,
                                                     len(jobs),
                                                     len(job['builds'])))
                future_builds = []
                nums = [b['number'] for b in job['builds']]
                for n in nums:
                    future_builds.append(
                        executor.submit(self._get_build, uri, job_name, n))

                for future in as_completed(future_builds):
                    try:
                        builds.append(future.result())
                    except Exception as e:
                        logger.error(
                            '(%s) Failed to save: %s' % (e, job_name))
        return builds

    def _get_build(self, uri, job_name, build_number):
        _oid = '%s #%s' % (job_name, build_number)

        _build = {}
        #_args = 'tree=%s' % ','.join(self.fields)
        _args = 'depth=1'
        _job_path = '/job/%s/%s' % (job_name, build_number)

        job_uri = '%s%s/%s?%s' % (uri, _job_path,
                                  self.api_path, _args)
        logger.debug('Loading (%s)' % job_uri)
        try:
            _page = rget(job_uri).content
            build_content = json.loads(_page,
                                       strict=False,
                                       object_hook=obj_hook)
        except Exception as e:
            logger.error('OOPS! (%s) %s' % (job_uri, e))
            build_content = {'load_error': e}

        _build['_oid'] = _oid
        _build['job_name'] = job_name
        _build['job_uri'] = job_uri
        _build['number'] = build_number
        _build.update(build_content)

        report_uri = '%s%s/testReport/%s?%s' % (uri,
                                                _job_path, self.api_path,
                                                _args)
        logger.debug('Loading (%s)' % report_uri)
        try:
            _page = rget(report_uri).content
            report_content = json.loads(_page,
                                        strict=False,
                                        object_hook=obj_hook)
        except Exception as e:
            logger.error('OOPS! (%s) %s' % (report_uri, e))
            report_content = {'load_error': e}

        _build['report_uri'] = report_uri
        _build['report'] = report_content
        return _build


if __name__ == '__main__':
    from metriquec.argparsers import cube_cli
    cube_cli(Build)
