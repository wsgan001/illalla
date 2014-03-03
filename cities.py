#! /usr/bin/python2
# vim: set fileencoding=utf-8
# from more_query import bbox_to_polygon
# from json import dumps
"""A list of cities with related information: bounding box, name, local
Euclidean projection."""
from string import ascii_lowercase as alphabet
import LocalCartesian as lc


def short_name(long_name):
    """Return normalized name of city"""
    return ''.join([c.lower() for c in long_name if c.lower() in alphabet])

NYC = [40.583, -74.040, 40.883, -73.767]
WAS = [38.8515, -77.121, 38.9848, -76.902]
SAF = [37.7123, -122.531, 37.84, -122.35]
ATL = [33.657, -84.529, 33.859, -84.322]
IND = [39.632, -86.326, 39.958, -85.952]
LAN = [33.924, -118.632, 34.313, -118.172]
SEA = [47.499, -122.437, 47.735, -122.239]
HOU = [29.577, -95.686, 29.897, -95.187]
SLO = [38.535, -90.320, 38.740, -90.180]
CHI = [41.645, -87.844, 42.020, -87.520]
LON = [51.475, -0.245, 51.597, 0.034]
PAR = [48.8186, 2.255, 48.9024, 2.414]
BER = [52.389, 13.096, 52.651, 13.743]
ROM = [41.8000, 12.375, 41.9848, 12.610]
PRA = [49.9777, 14.245, 50.1703, 14.660]
MOS = [55.584, 37.353, 55.906, 37.848]
AMS = [52.3337, 4.730, 52.4175, 4.986]
HEL = [60.1463, 24.839, 60.2420, 25.0200]
STO = [59.3003, 17.996, 59.3614, 18.162]
BAR = [41.3253, 2.1004, 41.4669, 2.240]
US = [NYC, WAS, SAF, ATL, IND, LAN, SEA, HOU, SLO, CHI]
EU = [LON, PAR, BER, ROM, PRA, MOS, AMS, HEL, STO, BAR]
NAMES = ['New York', 'Washington', 'San Francisco', 'Atlanta', 'Indianapolis',
         'Los Angeles', 'Seattle', 'Houston', 'St. Louis', 'Chicago',
         'London', 'Paris', 'Berlin', 'Rome', 'Prague', 'Moscow', 'Amsterdam',
         'Helsinki', 'Stockholm', 'Barcelona']
SHORT_KEY = [short_name(city) for city in NAMES]
INDEX = {short_name(city): _id for _id, city in enumerate(NAMES)}
middle = lambda bbox: (.5*(bbox[0] + bbox[2]), (.5*(bbox[1] + bbox[3])))
GEO_TO_2D = {name: lc.LocalCartesian(*middle(city)).forward
             for name, city in zip(SHORT_KEY, US+EU)}


if __name__ == '__main__':
    from random import uniform
    from geographiclib.geodesic import Geodesic
    EARTH = Geodesic.WGS84
    city = HOU
    name = 'houston'
    place = lambda: (uniform(city[0], city[2]), uniform(city[1], city[3]))
    for i in range(20):
        p1 = place()
        p2 = place()
        local_diff = GEO_TO_2D[name](p1) - GEO_TO_2D[name](p2)
        estimated_dst = lc.numpy.linalg.norm(local_diff[:2])
        estimated_dst_f = lc.numpy.linalg.norm(local_diff)
        real_dst = EARTH.Inverse(p1[0], p1[1], p2[0], p2[1])['s12']
        variation = 100*(estimated_dst-real_dst)/real_dst
        variation_f = 100*(estimated_dst_f-real_dst)/real_dst
        print('variation: {:.7f}% vs {:.7f}%'.format(variation, variation_f))
#     for cities in US+EU:
#         print(dumps(bbox_to_polygon(cities)))
