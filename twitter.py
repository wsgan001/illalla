﻿#! /usr/bin/python2
# vim: set fileencoding=utf-8
"""Retrieve checkins tweets"""
from timeit import default_timer as clock
from time import sleep
from datetime import datetime
import TwitterAPI as twitter
from api_keys import TWITTER_CONSUMER_KEY as consumer_key
from api_keys import TWITTER_CONSUMER_SECRET as consumer_secret
from api_keys import TWITTER_ACCESS_TOKEN as access_token
from api_keys import TWITTER_ACCESS_SECRET as access_secret
import twitter_helper as th
import arguments
ARGS = arguments.tweets_parser().parse_args()
DB = None
SAVE = None
if ARGS.mongodb:
    import CommonMongo as cm
    DB = cm.connect_to_db('foursquare', ARGS.host, ARGS.port)[0]
else:
    json = th.import_json()
import CheckinAPICrawler as cac
CRAWLER = cac.CheckinAPICrawler()
CITIES_TREE = th.obtain_tree()
from Queue import Queue
from threading import Thread
from utils import get_nested
import cities
import locale
locale.setlocale(locale.LC_ALL, 'C')  # to parse date
UTC_DATE = '%a %b %d %X +0000 %Y'
FullCheckIn = th.namedtuple('FullCheckIn', ['id', 'lid', 'uid', 'city', 'loc',
                                            'time', 'tid', 'tuid', 'msg'])
# the size of mongo bulk insert, in multiple of pool size
INSERT_SIZE = 7
CHECKINS_QUEUE = Queue((INSERT_SIZE+3)*cac.BITLY_SIZE)
# There is probably a cleaner version, but it is global because if
# read_twitter_stream fails, we still want to keep a accurate count of tweets
# seen so far
NB_TWEETS = 0
NUM_VALID = 0


def parse_tweet(tweet):
    """Return a CheckIn from `tweet` or None if it is not located in a valid
    city"""
    loc = get_nested(tweet, 'coordinates')
    city = None
    if not loc:
        # In that case, we would have to follow the link to know whether the
        # checkin falls within our cities but that's too costly so we drop it
        # (and introduce a bias toward open sharing users I guess)
        return None
    lon, lat = loc['coordinates']
    city = th.find_town(lat, lon, CITIES_TREE)
    # if not (city and city in cities.SHORT_KEY):
    #     return None
    tid = get_nested(tweet, 'id_str')
    urls = get_nested(tweet, ['entities', 'urls'], [])
    # short url of the checkin that need to be expand, either using bitly API
    # or by VenueIdCrawler. Once we get the full URL, we still need to request
    # 4SQ (500 per hours) to get info (or look at page body, which contains the
    # full checkin in a javascript field)
    fsq_urls = [url['expanded_url'] for url in urls
                if '4sq.com' in url['expanded_url']]
    if not fsq_urls:
        return None
    lid = str(fsq_urls[0])
    uid = get_nested(tweet, ['user', 'id_str'])
    msg = get_nested(tweet, 'text')
    try:
        time = datetime.strptime(tweet['created_at'], UTC_DATE)
        # time = cities.utc_to_local(city, time)
    except ValueError:
        print('time: {}'.format(tweet['created_at']))
        return None
    return FullCheckIn('', lid, '', city, loc, time, tid, uid, msg)


def post_process(checkins):
    """use `crawler` to follow URL within `checkins` and update them with
    information regarding the actual Foursquare checkin."""
    infos = CRAWLER.checkins_from_url([c.lid for c in checkins])
    if not infos:
        return None
    finalized = []
    global NUM_VALID
    for checkin, info in zip(checkins, infos):
        if info:
            converted = checkin._asdict()
            id_, uid, vid, time = info
            del converted['id']
            converted['_id'] = id_
            converted['uid'] = uid
            converted['lid'] = vid
            converted['time'] = time
            finalized.append(converted)
            NUM_VALID += 1
        CHECKINS_QUEUE.task_done()
    return finalized


def accumulate_checkins():
    """Call save checkin as soon as a batch is complete (or the last one was
    received)."""
    waiting_for_crawling = []
    while True:
        checkin = CHECKINS_QUEUE.get()
        if not checkin:
            # receive None, signaling end of the time allowed
            CHECKINS_QUEUE.task_done()
            break
        waiting_for_crawling.append(checkin)
        if len(waiting_for_crawling) == INSERT_SIZE*cac.BITLY_SIZE:
            status = save_checkins(post_process(waiting_for_crawling), SAVE)
            del waiting_for_crawling[:]
            # status is None when CRAWLER.checkins_from_url returns None,
            # which in turn means that Foursquare is in such a bad state that
            # it does not make sense to try to query it anymore.
            if status is None:
                break
    save_checkins(post_process(waiting_for_crawling), SAVE)


def save_checkins(complete, saving_method):
    """Save `complete` using `saving_method`."""
    if not complete:
        return None
    saving_method(complete)
    return True


def save_checkins_mongo(complete):
    """Save `complete` in DB."""
    try:
        DB.checkin.insert(complete, continue_on_error=True)
        print('insert {}'.format(len(complete)))
    except cm.pymongo.errors.DuplicateKeyError:
        pass
    except cm.pymongo.errors.OperationFailure as err:
        print(err, err.code)


def save_checkins_json(complete):
    """Save `complete` as JSON in a file."""
    now = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = 'tweets_{}.json'.format(now)
    msg = 'Save {} tweets in {}.'.format(len(complete), filename)
    try:
        for idx, checkin in enumerate(complete):
            fmt_time = checkin['time'].strftime('%Y-%m-%dT%H:%M:%SZ')
            complete[idx]['time'] = {'$date': fmt_time}
        with open(filename, 'w') as out:
            out.write(json.dumps(complete, ensure_ascii=False).replace('\/',
                                                                       '/'))
            cac.logging.info(msg)
    except (KeyboardInterrupt, SystemExit):
        raise
    except:
        msg = "Fail to save {} tweets.".format(len(complete))
        cac.logging.exception(msg)


def read_twitter_stream(client, end, logging_step=60):
    """Iterate over tweets and put those matched by parse_tweet in a queue,
    until current time is more than `end`. Log info every `logging_step` new
    valid candidate."""
    global NB_TWEETS
    req = client.request('statuses/filter', {'track': '4sq com'})
    new_tweet = 'get {}, {}/{}, {:.1f} seconds to go'
    nb_cand = 0
    for item in req.get_iterator():
        candidate = parse_tweet(item)
        NB_TWEETS += 1
        if candidate:
            CHECKINS_QUEUE.put_nowait(candidate)
            nb_cand += 1
            if nb_cand % logging_step == 0:
                cac.logging.info(new_tweet.format(candidate.tid,
                                                        nb_cand, NB_TWEETS,
                                                        end - clock()))
            if clock() >= end:
                CHECKINS_QUEUE.put_nowait(None)
                break

if __name__ == '__main__':
    # pylint: disable=C0103
    if DB:
        DB.checkin.ensure_index([('loc', cm.pymongo.GEOSPHERE),
                                 ('lid', cm.pymongo.ASCENDING),
                                 ('city', cm.pymongo.ASCENDING),
                                 ('time', cm.pymongo.ASCENDING)])
    SAVE = save_checkins_mongo if ARGS.mongodb else save_checkins_json
    api = twitter.TwitterAPI(consumer_key, consumer_secret,
                             access_token, access_secret)
    accu = Thread(target=accumulate_checkins, name='AccumulateCheckins')
    accu.daemon = True
    accu.start()
    start = clock()
    end = start + ARGS.duration*60*60
    failures = th.Failures(initial_waiting_time=2.0)
    while clock() < end:
        try:
            read_twitter_stream(api, end)
        except (KeyboardInterrupt, SystemExit):
            CHECKINS_QUEUE.put_nowait(None)
            raise
        except:
            msg = 'Fail to read or enqueue tweet\n'
            cac.logging.exception(msg)
            waiting_time = failures.fail()
            if clock() + waiting_time > end or \
               failures.recent_failures >= 5 or \
               not accu.is_alive():
                # We might as well quit right now, as stars are agains us
                CHECKINS_QUEUE.put_nowait(None)
                break
            msg = 'Will wait for {:.0f} seconds'.format(waiting_time)
            cac.logging.info(msg)
            failures.do_sleep()

    CHECKINS_QUEUE.join()
    report = 'insert {} valid checkins in {:.2f}s (out of {}).'
    print(report.format(NUM_VALID, clock() - start, NB_TWEETS))
    sleep(1)
