#! /usr/bin/python2
# vim: set fileencoding=utf-8
from timeit import default_timer as clock
import pycurl
import cStringIO
import re
import logging
import os
import foursquare
from api_keys import FOURSQUARE_ID as CLIENT_ID
from api_keys import FOURSQUARE_SECRET as CLIENT_SECRET
from RequestsMonitor import RequestsMonitor
logging.basicConfig(filename=os.path.expanduser('~/venue.log'),
                    level=logging.INFO,
                    format='%(asctime)s [%(levelname)s]: %(message)s')
POOL_SIZE = 30


class VenueIdCrawler():
    cpool = None
    one_shot = None
    claim_id = None
    multi = None
    pool_size = 0
    connections = 0
    results = {None: None}
    errors = []
    todo = []
    use_network = False
    client = None
    limitor = None
    checkin_url = None

    def __init__(self, pre_computed=None, use_network=False,
                 pool_size=POOL_SIZE):
        assert isinstance(pool_size, int) and pool_size > 0
        self.pool_size = pool_size
        self.one_shot = pycurl.Curl()
        self.claim_id = re.compile(r'claim\?vid=([0-9a-f]{24})')
        self.checkin_url = re.compile(r'([0-9a-f]{24})\?s=(\w+)')
        self.multi = pycurl.CurlMulti()
        self.cpool = [pycurl.Curl() for _ in range(self.pool_size)]
        self.todo = []
        self.use_network = use_network
        for c in self.cpool:
            c.setopt(pycurl.FOLLOWLOCATION, 1)
            c.setopt(pycurl.MAXREDIRS, 6)
            c.setopt(pycurl.NOBODY, 1)
        if pre_computed is not None:
            self.results = pre_computed
            self.results['None'] = None
        self.client = foursquare.Foursquare(CLIENT_ID, CLIENT_SECRET)
        self.limitor = RequestsMonitor(500)

    def venue_id_from_urls(self, urls):
        start = clock()
        nb_urls = len(urls)
        batch = []
        target = batch if self.use_network else self.todo
        for i, u in enumerate(urls):
            if u is not None and u not in self.results:
                target.append(u)
            if not self.use_network:
                continue
            if len(batch) == self.pool_size or i == nb_urls - 1:
                lstart = clock()
                self.prepare_request(batch)
                self.perform_request()
                batch = []
                logging.info('batch in {:.2f}s'.format(clock() - lstart))
        report = 'query {} urls in {:.2f}s, {} (total) errors'
        logging.info(report.format(len(urls), clock() - start,
                                   len(self.errors)))
        return [None if u not in self.results else self.results[u]
                for u in urls]

    def prepare_request(self, urls):
        assert len(urls) <= self.pool_size
        for i, u in enumerate(urls):
            self.cpool[i].setopt(pycurl.URL, u)
            self.cpool[i].url = u
            self.multi.add_handle(self.cpool[i])
            self.connections += 1

    def perform_request(self):
        while self.connections > 0:
            status = self.multi.select(0.3)
            if status == -1:  # timeout
                continue
            if status > 0:
                self.empty_queue()
            performing = True
            while performing:
                status, self.connections = self.multi.perform()
                if status is not pycurl.E_CALL_MULTI_PERFORM:
                    performing = False
        self.empty_queue()

    def empty_queue(self):
        _, ok, ko = self.multi.info_read()
        for failed in ko:
            self.errors.append((failed[0].url, failed[1]))
            self.multi.remove_handle(failed[0])
        for success in ok:
            self.results[success.url] = self.get_venue_id(success)
            self.multi.remove_handle(success)

    def get_venue_id(self, curl_object):
        if curl_object.getinfo(pycurl.HTTP_CODE) != 200:
            return None
        url = curl_object.getinfo(pycurl.EFFECTIVE_URL)
        id_ = url.split('/')[-1]
        if len(id_) >= 24 and '4' in id_[:6]:
            return self.expand_potential_checkin(id_)
        # we probably got a vanity url like https://foursquare.com/radiuspizza
        # thus we go there and try to find the link to claim this venue,
        # because it contains the numerical id.
        buf = cStringIO.StringIO()
        self.one_shot.setopt(pycurl.URL, url)
        self.one_shot.setopt(pycurl.WRITEFUNCTION, buf.write)
        self.one_shot.perform()
        body = buf.getvalue()
        del buf
        if self.one_shot.getinfo(pycurl.HTTP_CODE) != 200:
            return None
        match = self.claim_id.search(body)
        if match is None:
            return None
        return match.group(1)

    def expand_potential_checkin(self, id_):
        match = self.checkin_url.search(id_)
        if match is None:
            return None
        checkin, sig = match.group(1, 2)
        go, _ = self.limitor.more_allowed(self.client)
        if not go:
            return id_
        res = self.client.checkins(checkin, {'signature': sig})
        if 'checkin' in res:
            return res['checkin']['venue']['id']
        return None


def venue_id_from_url(c, url):
    """
    Return the id of the venue associated with short url
    >>> venue_id_from_url(pycurl.Curl(), 'http://4sq.com/31ZCjK')
    '44d17cecf964a5202b361fe3'
    """
    c.reset()
    c.setopt(pycurl.URL, url)
    c.setopt(pycurl.FOLLOWLOCATION, 1)
    c.setopt(pycurl.MAXREDIRS, 6)
    c.setopt(pycurl.NOBODY, 1)
    c.perform()
    if c.getinfo(pycurl.HTTP_CODE) == 200:
        return c.getinfo(pycurl.EFFECTIVE_URL).split('/')[-1]
    return None

if __name__ == '__main__':
    from persistent import load_var
    urls = ['http://4sq.com/1ZNmiJ', 'http://4sq.com/2z5p82',
            'http://4sq.com/31ZCjK', 'http://4sq.com/3iFEGH',
            'http://4sq.com/4ADi6k', 'http://4sq.com/4FFBOp',
            'http://4sq.com/4k1L7c', 'http://4sq.com/5DPD7A',
            'http://4sq.com/5NbLrk', 'http://4sq.com/67XL9k',
            'http://4sq.com/75SfNv', 'http://4sq.com/7DAVph',
            'http://4sq.com/7JaOFa', 'http://4sq.com/7sG6jW',
            'http://4sq.com/7yoatn', 'http://4sq.com/81eMd8',
            'http://4sq.com/8bg7q4', 'http://4sq.com/8gFJww',
            'http://4sq.com/8KuiUi', 'http://4sq.com/9cg9xg',
            'http://4sq.com/9E7CnF', 'http://4sq.com/9GoW57',
            'http://4sq.com/9hM2SE', 'http://4sq.com/9qN20H',
            'http://4sq.com/9yHXf0', 'http://4sq.com/alRmoX',
            'http://4sq.com/c7m20Y', 'http://4sq.com/cDCxsE',
            'http://4sq.com/ck4qtA', 'http://4sq.com/cXUN8F',
            'http://4sq.com/cYesTR', 'http://4sq.com/dlIcOc',
            'http://4sq.com/dy5um7', 'http://4sq.com/dz96EL',
            'http://4sq.com/31ZCjK', 'http://4sq.com/3iFEGH',
            'http://4sq.com/4ADi6k', 'http://4sq.com/4FFBOp',
            'http://4sq.com/4k1L7c', 'http://4sq.com/5DPD7A',
            'http://4sq.com/5NbLrk', 'http://4sq.com/67XL9k',
            'http://4sq.com/75SfNv', 'http://4sq.com/7DAVph',
            'http://4sq.com/7JaOFa', 'http://4sq.com/7sG6jW',
            'http://4sq.com/7yoatn', 'http://4sq.com/81eMd8',
            'http://4sq.com/8bg7q4', 'http://4sq.com/8gFJww',
            'http://4sq.com/8KuiUi', 'http://4sq.com/9cg9xg',
            'http://4sq.com/9E7CnF', 'http://4sq.com/9GoW57',
            'http://4sq.com/9hM2SE', 'http://4sq.com/9qN20H',
            'http://4sq.com/9yHXf0', 'http://4sq.com/alRmoX',
            'http://4sq.com/c7m20Y', 'http://4sq.com/cDCxsE',
            'http://4sq.com/ck4qtA', 'http://4sq.com/cXUN8F',
            'http://4sq.com/cYesTR', 'http://4sq.com/dlIcOc',
            'http://4sq.com/dy5um7', 'http://4sq.com/dz96EL',
            'http://t.co/3kGBr2l', 'http://t.co/90Fh8ks',
            'http://t.co/9COjxhy', 'http://t.co/axfykVI',
            'http://t.co/djzPO2S', 'http://t.co/gFaEd0N',
            'http://t.co/HEAq94l', 'http://t.co/Hl8jVOi',
            'http://t.co/iQ6yeYi', 'http://t.co/MkpAVDb',
            'http://t.co/Mu61K9b', 'http://t.co/n4kqQR0',
            'http://t.co/NN1xkiq', 'http://t.co/T88WGpO',
            'http://t.co/WQn3bFf', 'http://t.co/y8qxjsT',
            'http://t.co/ycbb5kt']
    checkins_url = ['https://fr.foursquare.com/tommiar/checkin/4d21eac35acaa35d8c03d435?s=plNfJpw51khCMN2yDrSfSl_68lY']
    gold = load_var('gold_url')
    start = clock()
    r = VenueIdCrawler()
    query_url = urls[:2*len(gold)]
    query_url = checkins_url
    res = r.venue_id_from_urls(query_url)
    res_dict = {u: i for u, i in zip(query_url, res)}
    print('{:.2f}s'.format(clock() - start))
    print(res_dict)
    # shared_items = set(gold.items()) & set(res_dict.items())
    # print('match with gold: {}/{}'.format(len(shared_items), len(gold)))
    # for g, m in zip(sorted(gold.items()), sorted(res_dict.items())):
    #     print(g, m)
