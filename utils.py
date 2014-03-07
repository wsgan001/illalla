#! /usr/bin/python2
# vim: set fileencoding=utf-8
from collections import Counter
from persistent import load_var
import json
from random import uniform
import CommonMongo as cm
from geographiclib.geodesic import Geodesic
EARTH = Geodesic.WGS84


def noise():
    return uniform(0, 1e-6)


def to_css_hex(color):
    """
    >>> to_css_hex([1, 0, 1, .7])
    '#ff00ff'
    """
    r = '#'
    for i in color[:-1]:
        c = hex(int(255*i))[2:]
        if len(c) == 2:
            r += c
        else:
            r += '0' + c
    return r


def photos_to_heat_dataset(city, precision=4, limit=300):
    photos = load_var(city)
    points = Counter([(round(p[0], precision), round(p[1], precision))
                      for p in photos])
    maxi = points.most_common(1)[0][1]
    dataset = [{'lat': p[1], 'lon': p[0], 'value': c}
               for p, c in points.most_common(limit)]
    json_dataset = json.dumps({'max': maxi, 'data': dataset})
    with open(city+'.js', 'w') as f:
        f.write('var {} = {}'.format(city, json_dataset))


def photos_to_cluster_dataset(city, limit=300):
    photos = load_var(city)
    points = [[p[0] + noise(), p[1] + noise(), 'Win!']
              for p in photos[:limit]]
    with open(city+'_cluster.js', 'w') as f:
        f.write('var {}_cluster = {}'.format(city, str(points)))


def output_checkins(city):
    """Write a JS array of all checkins in `city` with their hour."""
    checkins = cm.connect_to_db('foursquare')[0]['checkin']
    query = cm.build_query(city, venue=False, fields=['loc', 'time'])
    res = checkins.aggregate(query)['result']

    def format_checkin(checkin):
        """Extract location (plus jitter) and hour from checkin"""
        lng, lat = checkin['loc']['coordinates']
        hour = checkin['time'].hour
        return [lng + noise(), lat + noise(), hour]

    formated = [str(format_checkin(c)) for c in res]
    with open(city + '_fs.js', 'w') as output:
        output.write('var helsinki_fs = [\n')
        output.write(',\n'.join(formated))
        output.write('];')


def get_nested(dico, fields, default=None):
    """If the key hierarchy of `fields` exists in `dico`, return its value,
    otherwise `default`.
    >>> get_nested({'loc': {'type': 'city'}}, ['loc', 'type'])
    'city'
    >>> get_nested({'type': 'city'}, 'type')
    'city'
    >>> get_nested({'loc': {'type': 'city'}}, ['loc', 'lat']) is None
    True
    >>> get_nested({'loc': {'type': None}}, ['loc', 'type']) is None
    True
    >>> get_nested({'l': {'t': {'a': 'h'}}}, ['l', 't', 'a'])
    'h'
    >>> get_nested({'l': {'t': None}}, ['l', 't', 'a'], 0)
    0
    >>> get_nested({'names': {'symbols': 'euro'}}, ['names', 'urls'], [])
    []
    """
    if not hasattr(fields, '__iter__'):
        return dico.get(fields, default)
    current = dico
    is_last_field = lambda i: i == len(fields) - 1
    for index, field in enumerate(fields):
        if not hasattr(current, 'get'):
            return default if is_last_field(index) else current
        current = current.get(field, default if is_last_field(index) else {})
    return current


def geodesic_distance(point_1, point_2):
    """Return the distance in meters between two JSON Points."""
    assert 'coordinates' in point_1 and 'coordinates' in point_2
    p1_lon, p1_lat = point_1['coordinates']
    p2_lon, p2_lat = point_2['coordinates']
    return EARTH.Inverse(p1_lat, p1_lon, p2_lat, p2_lon)['s12']


def answer_to_dict(cursor, default=None):
    """Take a `cursor` resulting from a mongo find query and return a
    dictionary id: value (provided that there is only one other field) (or
    `default`)."""
    try:
        first = cursor.next()
    except StopIteration:
        return {}
    keys = first.keys()
    assert '_id' in keys and len(keys) == 2
    field_name = keys[(keys.index('_id') + 1) % 2]
    res = {first['_id']: first.get(field_name, default)}
    res.update({v['_id']: v.get(field_name, default) for v in cursor})
    return res


if __name__ == '__main__':
    import doctest
    doctest.testmod()
