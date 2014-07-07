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

Created on Sep 6, 2011

@author: ACrosby
'''
from collections import deque
import sys
import os
import logging
import traceback
from datetime import datetime
from dateutil.parser import parse
import dateutil.parser
import glob
import multiprocessing
import gc
import shutil
import time

try:
    import cPickle as pickle
except:
    import Pickle as pickle

import numpy as np

import netCDF4
from netCDF4 import Dataset as ncDataset
from netCDF4 import date2num

from sciwms.apps.wms.models import Dataset
from sciwms.libs.data import build_tree
import sciwms.util.cf as cf

import rtree

from django.conf import settings

import pyugrid

logger = multiprocessing.get_logger()

# default time units for CF data
TIME_UNITS = 'hours since 1970-01-01'

class FastRtree(rtree.Rtree):
    def dumps(self, obj):
        try:
            import cPickle
            return cPickle.dumps(obj,-1)
        except ImportError:
            super(FastRtree, self).dumps(obj)
            
def create_rtree_from_ug(ug, dataset_name):
    logger.info("Building Rtree Topology Cache for {0}".format(dataset_name))
    p = rtree.index.Property()
    p.overwrite = True
    p.storage   = rtree.index.RT_Disk
    p.Dimension = 2
    rtree_file = os.path.join(settings.TOPOLOGY_PATH, dataset_name + '.updating')
    def rtree_generator_function():
        for face_idx, node_list in enumerate(ug.faces):
            nodes = ug.nodes[node_list]
            xmin, ymin = np.min(nodes,0)
            xmax, ymax = np.max(nodes,0)
            yield (face_idx, (xmin,ymin,xmax,ymax), node_list)
    start = time.time()
    ridx = FastRtree(rtree_file,
                     rtree_generator_function(),
                     properties=p,
                     overwrite=True,
                     interleaved=True)
    logger.info("Built Rtree Topology Cache in {0} seconds.".format(time.time() - start))

    shutil.move(rtree_file+".dat",(rtree_file+".dat").replace('.updating',''))
    shutil.move(rtree_file+".idx",(rtree_file+".idx").replace('.updating',''))

# ==================================
def _update_topology_time(dataset_name, url):
    # TODO: time dimensions can be UNLIMITED (None)
    ''' mirrors the time dimension and variable from remote to local topology '''
    ''' NOTE: overwrites each time called '''
    remote = netCDF4.Dataset(url) 
    topology_path = os.path.join(settings.TOPOLOGY_PATH, dataset_name + ".nc")
    topology = netCDF4.Dataset(topology_path, mode='r+')

    # get remote time
    remote_time = cf.get_by_standard_name(remote, 'time')

    # create 'time' dimension and variable
    if remote_time is not None:
        topology.createDimension('time', remote_time.shape[0])
        if remote_time.ndim > 1:
            # remote NetCDF uses string-valued coordinate variable see http://www.unidata.ucar.edu/software/netcdf/docs/BestPractices.html#Coordinate Systems
            time = topology.createVariable('time', 'f8', ('time',), chunksizes=(remote_time.shape[0],), zlib=False, complevel=0)
            _str_data = remote_time[:, :]
            dates = [dateutil.parser.parse(_str_data[i, :].tostring()) for i in range(len(_str_data[:, 0]))]
            time[:] = netCDF4.date2num(dates, TIME_UNITS)
            time.units = TIME_UNITS
            time.setncattr('standard_name', 'time')
        else:
            ''' copy time variable as-is from remote NetCDF '''
            time = topology.createVariable('time', 'f8', ('time',), chunksizes=remote_time.shape, zlib=False, complevel=0)
            time[:] = remote_time[:]
            time.units = remote_time.units
            time.setncattr('standard_name', 'time')
    else:
        ''' remote NetCDF contains no time '''
        # TODO: why would we have a time dimension with 1?
        topology.createDimension('time', 1)
        time = topology.createVariable('time', 'f8', ('time',), chunksizes=(1,), zlib=False, complevel=0)
        time[:] = np.ones(1)
        time.units = TIME_UNITS
        time.setncattr('standard_name', 'time')

    topology.sync()
    topology.close()
    remote.close()

# =====================================
def create_topology(dataset_name, url):

    if url.endswith('.html'):
        url = url[:-5]

    try:
        logger.info('creating topology {0}'.format(url))
        remote = netCDF4.Dataset(url)
        ug = pyugrid.UGrid.from_nc_dataset(remote)
        logger.info("processing as UGRID")

        # -- create the local cache temp file
        topology_path = os.path.join(settings.TOPOLOGY_PATH, dataset_name+".nc")
        ug.save_as_netcdf(topology_path)

        # add time to UGRID topology files
        _update_topology_time(dataset_name, url)

        # create RTree
        create_rtree_from_ug(pyugrid.UGrid.from_ncfile(topology_path), dataset_name)
    except:
        #exc_type, exc_value, exc_traceback = sys.exc_info()
        #logger.error("Disabling Error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        #logger.info("non-UGRID")
        #logger.info('url: {0}'.format(url))
        create_topology_cgrid(dataset_name, url)

# ==================================        
def create_topology_cgrid(dataset_name, url):
    try:
        remote = netCDF4.Dataset(url)
        topology_path = os.path.join(settings.TOPOLOGY_PATH, dataset_name+".nc")
        #topology = netCDF4.Dataset(topology_path, mode="w", clobber=True)
        topology = netCDF4.Dataset(topology_path, mode="w")

        remote_longitude = cf.get_by_standard_name(remote, 'longitude')
        remote_latitude = cf.get_by_standard_name(remote, 'latitude')

        if remote_latitude.ndim > 1:
            igrid = remote_latitude.shape[0]
            jgrid = remote_latitude.shape[1]
            grid = 'cgrid'
        else:
            # i/j backwards? isn't i == longitude and j == latitide? check where igrid/jgrid used
            grid = 'rgrid'
            #igrid = nc.variables[latname].shape[0]
            #jgrid = nc.variables[lonname].shape[0]
            igrid = remote_latitude.shape[0]
            jgrid = remote_longitude.shape[0]

        latchunk, lonchunk = (igrid, jgrid,), (igrid, jgrid,)

        topology.createDimension('igrid', igrid)
        topology.createDimension('jgrid', jgrid)

        latitude = topology.createVariable('latitude', 'f', ('igrid', 'jgrid',), chunksizes=latchunk, zlib=False, complevel=0)
        latitude.setncattr('standard_name', 'latitude')

        longitude = topology.createVariable('longitude', 'f', ('igrid', 'jgrid',), chunksizes=lonchunk, zlib=False, complevel=0)
        longitude.setncattr('standard_name', 'longitude')

        # for CF keeping these all 0-360
        lon = remote_longitude[:]
        lon[lon>180] = lon[lon>180]-360.0

        if grid == 'rgrid':
            #longitude[:], latitude[:] = np.meshgrid(remote_longitude[:], remote_latitude[:])
            longitude[:], latitude[:] = np.meshgrid(lon[:], remote_latitude[:])
            grid = 'cgrid'
        else:
            #longitude[:] = remote_longitude[:]
            longitude[:] = lon[:]
            latitude[:] = remote_latitude[:]

        # TODO: why is this a while statement
        while not 'grid' in topology.ncattrs():
            topology.__setattr__('grid', 'cgrid')
            topology.sync()

        topology.sync()
        topology.close()
        remote.close()

        # add time
        _update_topology_time(dataset_name, url)

        # TODO: why all this moving?
        shutil.move(topology_path, topology_path.replace(".updating", ""))
        if not ((os.path.exists(topology_path.replace(".updating", "").replace(".nc", '_nodes.dat')) and os.path.exists(topology_path.replace(".updating", "").replace(".nc", "_nodes.idx")))):
            build_tree.build_from_nc(topology_path.replace(".updating", ""))

    except Exception:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error("Disabling Error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
#
#
#


def create_topology_from_config():
    """
    Initialize topology upon server start up for each of the datasets listed in LOCALDATASETPATH dictionary
    """
    for dataset in Dataset.objects.all():
        print "Adding: " + dataset["name"]
        create_topology(dataset["name"], dataset["uri"])


def update_datasets():
    for d in Dataset.objects.all():
        try:
            logger.info("Updating %s" % d.name)
            update_dataset_cache(d)
        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.error("Disabling Error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))


def update_dataset_cache(dataset):
    try:
        try:
            filemtime = datetime.fromtimestamp(os.path.getmtime(os.path.join(settings.TOPOLOGY_PATH, dataset.name + ".nc")))
            try:
                create_topology(dataset.name, dataset.path())
            except Exception:
                # TODO: remove this or use a logging statement
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logger.error("Disabling Error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        except Exception:
            logger.info("No cache found, Initializing: " + dataset.path())
            create_topology(dataset.name, dataset.path())

    except Exception:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error("Disabling Error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
