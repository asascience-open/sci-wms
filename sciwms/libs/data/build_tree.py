'''
COPYRIGHT 2010 RPS ASA

This file is part of SCI-WMS.

    SCI-WMS is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    SCI-WMS is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with SCI-WMS.  If not, see <http://www.gnu.org/licenses/>.
'''

import sys
import netCDF4
from rtree import index
from datetime import datetime

import sciwms.util.cf as cf

def build_from_nc(filename):

    # Make this True to enable timing
    timing = False

    if timing:
        timer = datetime.now()

    nc = netCDF4.Dataset(filename)
    if nc.grid == 'cgrid':
        latitude = cf.get_by_standard_name(nc, 'latitude')[:]
        longitude = cf.get_by_standard_name(nc, 'longitude')[:]
        nc.close()
        def generator_nodes():
            c = -1
            for row in range(longitude.shape[0]):
                for col in range(longitude.shape[1]):
                    coord = (longitude[row, col], latitude[row, col], longitude[row, col], latitude[row, col],)
                    c += 1
                    #yield(c, coord, ((row,), (col,)))
                    yield(c, coord, ((col,), (row,)))
                    #yield(c, coord, (row,col))
        filename = filename[:-3]
        tree = index.Index(filename+'_nodes', generator_nodes(), overwrite=True)
        if timing:
            print (datetime.now()-timer).seconds  # How long did it take to add the points
        tree.close()
