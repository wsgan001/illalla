#! /usr/bin/python2
# vim: set fileencoding=utf-8
"""Print statistics about database."""
import prettytable as pt
from datetime import datetime as dt
import CommonMongo as cm
import locale
try:
    locale.setlocale(locale.LC_ALL, 'en_US')
except locale.Error:
    locale.setlocale(locale.LC_ALL, '')


def ordered(counts, cities):
    """Return `counts` ordered by cities."""
    as_dict = {v['_id']: v['count'] for v in counts}
    count = [as_dict.get(city, 0) for city in cities]
    fmt = lambda v: locale.format('%d', v, grouping=True)
    return [fmt(c) if c > 10 else '' for c in count]


if __name__ == '__main__':
    #pylint: disable=C0103
    foursquare, client = cm.connect_to_db('foursquare')
    checkins = foursquare.checkin
    venues = foursquare.venue
    photos = client.world.photos
    newer = dt(2014, 1, 1)
    t = pt.PrettyTable()
    t.junction_char = '|'
    checkin = checkins.aggregate([{'$match': {'time': {'$lt': newer}}},
                                  {'$project': {'city': 1}},
                                  {'$group': {'_id': '$city',
                                              'count': {'$sum': 1}}},
                                  {'$sort': {'count': -1}}])['result']
    located = checkins.aggregate([{'$match': {'lid': {'$ne': None},
                                              'time': {'$lt': newer}}},
                                  {'$project': {'city': 1}},
                                  {'$group': {'_id': '$city',
                                              'count': {'$sum': 1}}}])
    newest = checkins.aggregate([{'$match': {'time': {'$gt': newer}}},
                                 {'$project': {'city': 1}},
                                 {'$group': {'_id': '$city',
                                             'count': {'$sum': 1}}}])
    venue = venues.aggregate([{'$project': {'city': 1}},
                              {'$group': {'_id': '$city',
                                          'count': {'$sum': 1}}}])
    order = [ck['_id'] for ck in checkin]
    flickr = photos.aggregate([{'$project': {'hint': 1}},
                               {'$group': {'_id': '$hint',
                                           'count': {'$sum': 1}}}])
    t.add_column('city', [cm.cities.FULLNAMES[n] for n in order], 'l')
    t.add_column('ICWS checkins', ordered(checkin, order), 'r')
    t.add_column('with venues', ordered(located['result'], order), 'r')
    t.add_column('photos', ordered(flickr['result'], order), 'r')
    t.add_column('venues', ordered(venue['result'], order), 'r')
    t.add_column('new checkins', ordered(newest['result'], order), 'r')
    table = str(t)
    line_size = len(table)/(len(order)+4)
    start = table.find('\n')+1
    end = table.find('\n', -int(1.5*line_size))
    with open('status.md', 'w') as status:
        status.write(table[start:end])
