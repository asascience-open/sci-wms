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

!!!THIS IS NOT A SCRIPT ANYMORE!!!
'''
from collections import deque
import sys
import os
import logging
import traceback
from datetime import datetime
from dateutil.parser import parse
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

from netCDF4 import Dataset as ncDataset
from netCDF4 import date2num

from sciwms.apps.wms.models import Dataset
from sciwms.libs.data import build_tree
import sciwms.util.cf as cf

import rtree

from django.conf import settings

import pyugrid

output_path = os.path.join(settings.PROJECT_ROOT, 'logs', 'sciwms_wms.log')
# Set up Logger
logger = multiprocessing.get_logger()
logger.setLevel(logging.INFO)
handler = logging.FileHandler(output_path)
formatter = logging.Formatter(fmt='[%(asctime)s] - <<%(levelname)s>> - |%(message)s|')
handler.setFormatter(formatter)
logger.addHandler(handler)

time_units = 'hours since 1970-01-01'

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
    # p.filename  = os.path.join(settings.TOPOLOGY_PATH, dataset_name)
    p.storage   = rtree.index.RT_Disk
    p.Dimension = 2

    rtree_file = os.path.join(settings.TOPOLOGY_PATH, dataset_name + '.updating')
    # rtree_tmp_file = rtree_file + 'update'
    
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
    
    
def create_topology(dataset_name, url, lat_var='lat', lon_var='lon'):

    if url.endswith('.html'):
        url = url[:-5]

    try:
        logger.info("Trying pyugrid")
        #try to load ugrid
        ug = pyugrid.UGrid.from_ncfile(url)

        logger.info("Identified as UGrid---Using pyugrid to cache")
        
        #create the local cache temp file
        nclocalpath = os.path.join(settings.TOPOLOGY_PATH, dataset_name+".nc.updating")
        ug.save_as_netcdf(nclocalpath)
        
        #move local cache temp to final destination(overwrite existing)
        shutil.move(nclocalpath, nclocalpath.replace(".updating", ""))

        create_rtree_from_ug(ug, dataset_name)
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.info("Cannot open with pyugrid: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        logger.info("Trying old sciwms method")
        create_topology_cgrid(dataset_name, url, lat_var='lat', lon_var = 'lon')
    finally:
        #release unreferenced memory
        gc.collect()
        
def create_topology_cgrid(dataset_name, url, lat_var='lat', lon_var='lon'):
    try:
        #with s1:
        nclocalpath = os.path.join(settings.TOPOLOGY_PATH, dataset_name+".nc.updating")
        nc = ncDataset(url)
        nclocal = ncDataset(nclocalpath, mode="w", clobber=True)

        logger.info("identified as grid")

        nclon = cf.get_by_standard_name(nc, 'longitude')
        nclat = cf.get_by_standard_name(nc, 'latitude')
        nctime = cf.get_by_standard_name(nc, 'time')

#        latname, lonname = lat_var, lon_var
#        if latname not in nc.variables:
#            for key in nc.variables.iterkeys():
#                try:
#                    nc.variables[key].__getattr__('units')
#                    temp_units = nc.variables[key].units
#                    if (not '_u' in key) and (not '_v' in key) and (not '_psi' in key):
#                        if 'degree' in temp_units:
#                            if 'east' in temp_units:
#                                lonname = key
#                            elif 'north' in temp_units:
#                                latname = key
#                            else:
#                                raise ValueError("No valid coordinates found in source netcdf file")
#                except:
#                    pass
        if nclat.ndim > 1:
            igrid = nclat.shape[0]
            jgrid = nclat.shape[1]
            grid = 'cgrid'
        else:
            # i/j backwards? isn't i == longitude and j == latitide? check where igrid/jgrid used
            grid = 'rgrid'
            #igrid = nc.variables[latname].shape[0]
            #jgrid = nc.variables[lonname].shape[0]
            igrid = nclat.shape[0]
            jgrid = nclon.shape[0]
        latchunk, lonchunk = (igrid, jgrid,), (igrid, jgrid,)
        logger.info("native grid style identified")
        nclocal.createDimension('igrid', igrid)
        nclocal.createDimension('jgrid', jgrid)
        #if "time" in nc.variables:
        if nctime is not None:
            #nclocal.createDimension('time', nc.variables['time'].shape[0])
            nclocal.createDimension('time', nctime.shape[0])
            #if nc.variables['time'].ndim > 1:
            if nctime.ndim > 1:
                time = nclocal.createVariable('time', 'f8', ('time',), chunksizes=(nctime.shape[0],), zlib=False, complevel=0)
            else:
                time = nclocal.createVariable('time', 'f8', ('time',), chunksizes=nctime.shape, zlib=False, complevel=0)
        else:
            nclocal.createDimension('time', 1)
            time = nclocal.createVariable('time', 'f8', ('time',), chunksizes=(1,), zlib=False, complevel=0)

        lat = nclocal.createVariable('lat', 'f', ('igrid', 'jgrid',), chunksizes=latchunk, zlib=False, complevel=0)
        lon = nclocal.createVariable('lon', 'f', ('igrid', 'jgrid',), chunksizes=lonchunk, zlib=False, complevel=0)
        logger.info("variables created in cache")
        lontemp = nclon[:]
        lontemp[lontemp > 180] = lontemp[lontemp > 180] - 360

        if grid == 'rgrid':
            lon[:], lat[:] = np.meshgrid(lontemp, nclat[:])
            grid = 'cgrid'
        else:
            lon[:] = lontemp
            lat[:] = nclat[:]
        if nctime is not None:
            if nctime.ndim > 1:
                _str_data = nctime[:, :]
                #print _str_data.shape, type(_str_data), "''", str(_str_data[0,:].tostring().replace(" ","")), "''"
                dates = [parse(_str_data[i, :].tostring()) for i in range(len(_str_data[:, 0]))]
                time[:] = date2num(dates, time_units)
                time.units = time_units
            else:
                time[:] = nctime[:]
                time.units = nctime.units
        else:
            time[:] = np.ones(1)
            time.units = time_units
        logger.info("data written to file")
        while not 'grid' in nclocal.ncattrs():
            nclocal.__setattr__('grid', 'cgrid')
            nclocal.sync()
        nclocal.sync()

        shutil.move(nclocalpath, nclocalpath.replace(".updating", ""))
        if not ((os.path.exists(nclocalpath.replace(".updating", "").replace(".nc", '_nodes.dat')) and os.path.exists(nclocalpath.replace(".updating", "").replace(".nc", "_nodes.idx")))):
            #with s1:
            build_tree.build_from_nc(nclocalpath.replace(".updating", ""))
        if grid == 'False':
            if not os.path.exists(nclocalpath.replace(".updating", "")[:-3] + '.domain'):
                #with s2:
                create_domain_polygon(nclocalpath.replace(".updating", ""))

    except Exception:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error("Disabling Error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
        try:
            nclocal.close()
        except:
            pass
        try:
            nc.close()
        except:
            pass
        if os.path.exists(nclocalpath):
            os.unlink(nclocalpath)
        raise
    finally:
        nclocal.close()
        nc.close()


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
            filemtime = datetime.fromtimestamp(
                os.path.getmtime(
                    os.path.join(
                        settings.TOPOLOGY_PATH, dataset.name + ".nc"
                    )))
            if dataset.keep_up_to_date:
                try:
                    nc = ncDataset(dataset.path())
                    topo = ncDataset(os.path.join(settings.TOPOLOGY_PATH, dataset.name+".nc"))

                    time1 = cf.get_by_standard_name(nc, 'time')[-1]
                    time2 = topo.variables['time'][-1]
                    if time1 != time2:
                        logger.info("Updating: " + dataset.path())
                        create_topology(dataset.name, dataset.path(), dataset.latitude_variable or 'lat', dataset.longitude_variable or 'lon')
                    else:
                        logger.info("No new time values found in dataset, nothing to update!")
                except Exception:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    logger.error("Disabling Error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
                finally:
                    nc.close()
                    topo.close()
            else:
                logger.info("Dataset not marked for update ('keep_up_to_date' is False).  Not doing anything.")
        except Exception:
            logger.info("No cache found, Initializing: " + dataset.path())
            create_topology(dataset.name, dataset.path(), dataset.latitude_variable or 'lat', dataset.longitude_variable or 'lon')

    except Exception:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error("Disabling Error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))


def create_domain_polygon(filename):
    from shapely.geometry import Polygon
    from shapely.ops import cascaded_union

    nc = ncDataset(filename)
    nv = nc.variables['nv'][:, :].T-1
    #print np.max(np.max(nv))
    latn = nc.variables['lat'][:]
    lonn = nc.variables['lon'][:]
    lon = nc.variables['lonc'][:]
    lat = nc.variables['latc'][:]
    #print lat, lon, latn, lonn, nv
    index_pos = np.asarray(np.where(
        (lat <= 90) & (lat >= -90) &
        (lon <= 180) & (lon > 0),)).squeeze()
    index_neg = np.asarray(np.where(
        (lat <= 90) & (lat >= -90) &
        (lon < 0) & (lon >= -180),)).squeeze()
    #print np.max(np.max(nv)), np.shape(nv), np.shape(lonn), np.shape(latn)
    if len(index_pos) > 0:
        p = deque()
        p_add = p.append
        for i in index_pos:
            flon, flat = lonn[nv[i, 0]], latn[nv[i, 0]]
            lon1, lat1 = lonn[nv[i, 1]], latn[nv[i, 1]]
            lon2, lat2 = lonn[nv[i, 2]], latn[nv[i, 2]]
            if flon < -90:
                flon = flon + 360
            if lon1 < -90:
                lon1 = lon1 + 360
            if lon2 < -90:
                lon2 = lon2 + 360
            p_add(Polygon(((flon, flat),
                           (lon1, lat1),
                           (lon2, lat2),
                           (flon, flat),)))
        domain_pos = cascaded_union(p)
    if len(index_neg) > 0:
        p = deque()
        p_add = p.append
        for i in index_neg:
            flon, flat = lonn[nv[i, 0]], latn[nv[i, 0]]
            lon1, lat1 = lonn[nv[i, 1]], latn[nv[i, 1]]
            lon2, lat2 = lonn[nv[i, 2]], latn[nv[i, 2]]
            if flon > 90:
                flon = flon - 360
            if lon1 > 90:
                lon1 = lon1 - 360
            if lon2 > 90:
                lon2 = lon2 - 360
            p_add(Polygon(((flon, flat),
                           (lon1, lat1),
                           (lon2, lat2),
                           (flon, flat),)))
        domain_neg = cascaded_union(p)
    if len(index_neg) > 0 and len(index_pos) > 0:
        from shapely.prepared import prep
        domain = prep(cascaded_union((domain_neg, domain_pos,)))
    elif len(index_neg) > 0:
        domain = domain_neg
    elif len(index_pos) > 0:
        domain = domain_pos
    else:
        logger.info(nc.__str__())
        logger.info(lat)
        logger.info(lon)
        logger.error("Domain file creation - No data in topology file Length of positive:%u Length of negative:%u" % (len(index_pos), len(index_neg)))
        raise ValueError("No data in file")

    f = open(filename[:-3] + '.domain', 'w')
    pickle.dump(domain, f)
    f.close()
    nc.close()
