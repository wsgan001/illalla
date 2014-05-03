#! /usr/bin/python2
# vim: set fileencoding=utf-8
"""Functions used in twitter scrapper main code."""
import functools
from timeit import default_timer as clock
import time
import utils as u
import pytz
import ujson
from datetime import datetime, timedelta


def import_json():
    """Return a json module (first trying ujson then simplejson and finally
    json from standard library)."""
    try:
        import ujson as json
    except ImportError:
        # try:
        #     import simplejson as json
        # except ImportError:
        #     import json
        # I cannot make the others two work with utf-8
        raise
    return json


def log_exception(log, default=None, reraise=False):
    """If `func` raises an exception, log it to `log`. By default, assume it's
    not critical and thus resume execution by returning `default`, except if
    `reraise` is True."""
    def actual_decorator(func):
        """Real decorator, with no argument"""
        @functools.wraps(func)
        def wrapper(*args, **kwds):
            """Wrapper"""
            try:
                return func(*args, **kwds)
            except (KeyboardInterrupt, SystemExit):
                raise
            except:
                log.exception("")
                if reraise:
                    raise
                return default
        return wrapper
    return actual_decorator


class Failures(object):
    """Keep track of Failures."""
    def __init__(self, initial_waiting_time):
        """`initial_waiting_time` is in minutes."""
        self.total_failures = 0
        self.last_failure = clock()
        self.initial_waiting_time = float(initial_waiting_time)*60.0
        self.reset()

    def reset(self):
        """Restore initial state with no recent failure."""
        self.recent_failures = 0
        self.waiting_time = self.initial_waiting_time

    def fail(self):
        """Register a new failure and return a reasonable time to wait"""
        if self.has_failed_recently():
            # Hopefully the golden ration will bring us luck next time
            self.waiting_time *= 1.618
        else:
            self.reset()
        self.total_failures += 1
        self.recent_failures += 1
        self.last_failure = clock()
        return self.waiting_time

    def has_failed_recently(self, small=3600):
        """Has it failed in the last `small` seconds?"""
        return self.total_failures > 0 and clock() - self.last_failure < small

    def do_sleep(self):
        """Indeed perform waiting."""
        time.sleep(self.waiting_time)


def parse_json_checkin(json, url=None):
    """Return salient info about a Foursquare checkin `json` that can be
    either JSON text or already parsed as a dictionary."""
    if not json:
        return None
    if not isinstance(json, dict):
        try:
            checkin = ujson.loads(json)
        except (TypeError, ValueError) as not_json:
            print(not_json, json, url)
            return None
    else:
        checkin = json['checkin']
    uid = u.get_nested(checkin, ['user', 'id'])
    vid = u.get_nested(checkin, ['venue', 'id'])
    time = u.get_nested(checkin, 'createdAt')
    offset = u.get_nested(checkin, 'timeZoneOffset', 0)
    if None in [uid, vid, time]:
        return None
    time = datetime.fromtimestamp(time, tz=pytz.utc)
    # by doing this, the date is no more UTC. So why not put the correct
    # timezone? Because in that case, pymongo will convert to UTC at
    # insertion. Yet I want local time, but without doing the conversion
    # when the result comes back from the DB.
    time += timedelta(minutes=offset)
    return int(uid), str(vid), time
