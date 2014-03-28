#! /usr/bin/python2
# vim: set fileencoding=utf-8
"""Get checkin info from 4sq.com short url."""
import ujson
from lxml import etree
PARSER = etree.HTMLParser()
XPATH_GET_SCRIPT = '//*[@id="container"]/script'
import VenueIdCrawler as vc
import pytz
from datetime import datetime, timedelta
from utils import get_nested


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
    uid = get_nested(checkin, ['user', 'id'])
    vid = get_nested(checkin, ['venue', 'id'])
    time = get_nested(checkin, 'createdAt')
    offset = get_nested(checkin, 'timeZoneOffset', 0)
    if None in [uid, vid, time]:
        return None
    time = datetime.fromtimestamp(time, tz=pytz.utc)
    # by doing this, the date is no more UTC. So why not put the correct
    # timezone? Because in that case, pymongo will convert to UTC at
    # insertion. Yet I want local time, but without doing the conversion
    # when the result comes back from the DB.
    time += timedelta(minutes=offset)
    return int(uid), str(vid), time


class CheckinCrawler(vc.VenueIdCrawler):
    """Get checkins info by expanding 4sq.com short urls."""
    def __init__(self, pool_size=vc.POOL_SIZE):
        vc.VenueIdCrawler.__init__(self, None, True, pool_size)
        self.results = {}

    def venue_id_from_urls(self, urls):
        assert False, "call checkins_from_url instead"

    def checkins_from_url(self, urls):
        """Return info from all url in `urls`"""
        start = vc.clock()
        nb_urls = len(urls)
        batch = []
        for i, url in enumerate(urls):
            batch.append(url)
            if len(batch) == self.pool_size or i == nb_urls - 1:
                self.prepare_request(batch)
                self.perform_request()
                del batch[:]
        report = 'query {} urls in {:.2f}s, {} (total) errors'
        vc.logging.info(report.format(len(urls), vc.clock() - start,
                                      len(self.errors)))
        return [self.results.pop(url, None) for url in urls]

    def get_venue_id(self, curl_object):
        return self.get_checkin_info(curl_object)

    def get_checkin_info(self, curl_object):
        """Analyze the answer from `curl_object` to return checkin id, user id,
        venue id and checkin local time."""
        if curl_object.getinfo(vc.pycurl.HTTP_CODE) != 200:
            return None
        url = curl_object.getinfo(vc.pycurl.EFFECTIVE_URL)
        id_ = url.split('/')[-1]
        match = self.checkin_url.match(id_)
        if not match:
            return None
        cid, sig = match.group(1, 2)
        tree = etree.fromstring(curl_object.buf.getvalue(), PARSER)
        script = tree.xpath(XPATH_GET_SCRIPT)
        if not script:
            return None
        # the HTML contains a script that in turn has a checkin JSON
        # object between these two indices.
        checkin = parse_json_checkin(script[0].text[76:-118], url)
        if not checkin:
            return None
        uid, vid, time = checkin
        return cid + '?s=' + sig, uid, vid, time

if __name__ == '__main__':
    # pylint: disable=C0103
    cc = CheckinCrawler()
    urls = ['http://4sq.com/1mShn3O']
    res = cc.checkins_from_url(urls)
    print(res)
