"""
This is /sciwms/apps/wms/get_map.py
"""
import logging
import multiprocessing
import os
import sys
import traceback

from django.conf import settings
from django.http import HttpResponse
from django.core.exceptions import ObjectDoesNotExist

import numpy as np
import netCDF4

import pyproj
import pyugrid

from . import wms_handler
from .matplotlib_handler import blank_canvas, quiver_response, get_nearest_start_time, contourf_response
from .models import Dataset as dbDataset
from ...util import cf, get_pyproj

import rtree
from ...libs.data.caching import FastRtree


logger = multiprocessing.get_logger()
EPSG4326 = pyproj.Proj(init='EPSG:4326')

def getMap(request, dataset):
    """
    the meat and bones of getMap
    """
    response = HttpResponse(content_type='image/png')

    # direct the service to the dataset
    url = dbDataset.objects.get(name=dataset).path()

    datasetnc = netCDF4.Dataset(url,'r')

    datestart, dateend = wms_handler.get_date_start_end(request)
    
    try:
        from .matplotlib_handler import get_nearest_start_time
        time = get_nearest_start_time(datasetnc, datestart)
    except:
        time = 0
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.info("Dataset doesn't contain temporal dimension: "
                    + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))

    t = time
    layer = [0] # vertical layer, WMS elevation
    z = wms_handler.get_elevation(request)

    variables = wms_handler.get_layers(request)

    # PROJECTED COORDINATES
    xmin, ymin, xmax, ymax = wms_handler.get_bbox(request)
    
    width, height = wms_handler.get_width_height(request)

    # PROJECT COORDINATES TO LAT/LON
    #proj = get_pyproj(request)
    #lonmin, latmin = proj(xmin, ymin, inverse=True)
    #lonmax, latmax = proj(xmax, ymax, inverse=True)
    CRS = get_pyproj(request)
    lonmin, latmin = pyproj.transform(CRS, EPSG4326, xmin, ymin)
    lonmax, latmax = pyproj.transform(CRS, EPSG4326, xmax, ymax)
    #logger.info("lonmin, latmin: {0} {1}".format(lonmin, latmin))
    #logger.info("lonmax, latmax: {0} {1}".format(lonmax, latmax))

    try:
        from .matplotlib_handler import get_lat_lon_subset_idx, get_nv_subset_idx, get_nearest_start_time
        import matplotlib.tri as Tri
        
        topology_path = os.path.join(settings.TOPOLOGY_PATH, dataset + '.nc')
        ug = pyugrid.UGrid.from_ncfile(topology_path)

        lon = ug.nodes[:,0]
        lat = ug.nodes[:,1]
        #logger.info('lon max/min: {0} {1}'.format(lon.max(), lon.min()))
        #logger.info('lon max/min: {0} {1}'.format(lat.max(), lat.min()))
        
        sub_idx = get_lat_lon_subset_idx(lon,lat,lonmin,latmin,lonmax,latmax)
        nv  = ug.faces[:]

        nv_subset_idx = get_nv_subset_idx(nv, sub_idx)

        #if no traingles insersect the field of view, return a transparent tile
        if (len(sub_idx) == 0) or (len(nv_subset_idx) == 0):
            logger.info("No triangles in field of view, returning empty tile.")
            canvas = blank_canvas(width,height)
            canvas.print_png(response)
            return response

        triang_subset = Tri.Triangulation(lon,lat,triangles=nv[nv_subset_idx])
        #logger.info('triang_subset.x: {0}'.format(triang_subset.x))
        #logger.info('triang_subset.y: {0}'.format(triang_subset.y))

        time = get_nearest_start_time(datasetnc, datestart)
        #logger.info('time index: {0}'.format(time))
            
        # some short names for indexes
        t = time
        z = layer[0] #TODO: change 'layer', bad terminology here w WMS LAYER meaning something else
        #z = 0

        # BM: updating here, where we're working with the data, no longer using the varname, but the UI name and need to get by standard_name
        # here's what's happening:
        #     - above we have established the indexes of interest (time,spatial,vertical) for the rendered tile
        #     - we need use these to get the subset of data via DAP to actually plot
        #
        #     being updated 20140801 is the variable name passed via WMS 'LAYERS' then changed to 'variables' (eg. ssh or u,v)
        #         need to be converted to the CF standard_name, then the netCDF4.Variable object needs to be obtained using that standard_name
        #         once we (if we) have that Variable, we can subset the data appropriately and plot
        #
        # TODO: drop this 'variables' nonsense, keep the request.GET[] content in WMS terms, this is a WMS service

        # scalar
        if len(variables) == 1:

            v = variables[0] # because it comes in as list, just using var for consistency with getFeatureInfo
            # get Variable using CF standard_name attribute
            if v == None:
                logger.warning('requested LAYERS %s, no map exists to CF standard_name' % var)
                canvas = blank_canvas(width, height)
                canvas.print_png(response)
                return response
            
            variable = cf.get_by_standard_name(datasetnc, v)

            data_obj = variable

            # TODO: UGRID[location] == face
            ## if location is 'face'
            #location = variable.__dict__.get('location', None)
            #if location == 'face':
            #    lat = np.mean(lat[nv.flatten()].reshape(nv.shape),1)
            #    lon = np.mean(lon[nv.flatten()].reshape(nv.shape),1)

            # faster to grab all data then to grab only subindicies from server
            if (len(data_obj.shape) == 3) and (time != None):
                data = data_obj[t,z,:]
            elif (len(data_obj.shape) == 2) and (time != None):
                data = data_obj[t,:]
            elif len(data_obj.shape) == 1:
                data = data_obj[:]
            else:
                logger.info("Dimension Mismatch: data_obj.shape == {0} and time = {1}".format(data_obj.shape, time))
                canvas = blank_canvas(width, height)
                canvas.print_png(response)
                return response
            
            import matplotlib_handler
            try:
                from . matplotlib_handler import tricontourf_response
                response = tricontourf_response(triang_subset, data, request)
            except:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logger.info("getMap import error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            return response

        # vector
        elif len(variables) == 2:

            variable = [cf.get_by_standard_name(datasetnc, v) for v in variables]

            if None in variable:
                logger.warning('variable not found for at least these'.format(variables))
                canvas = blank_canvas(width, height)
                canvas.print_png(response)
                return response

            # UGRID data has momentum (u,v) either on node (AKA vertices, eg. ADCIRC) or face (AKA triangle, eg. FVCOM/SELFE)
            #     check the location attribute of the UGRID variable to determine which lon/lat to use (if face, need a different set)
            location = set([v.__dict__.get('location', None) for v in variable])
            if len(location) > 1:
                logger.info("UGRID vector component variables require same 'location' attribute")
                canvas = blank_canvas(width, height)
                canvas.print_png(response)
                return response
            
            # hacky to do here, but in rush and it doesn't appear that replacing these within this scope will cause any problems
            if list(location)[0] == 'face':
                lat = np.mean(lat[nv.flatten()].reshape(nv.shape),1)
                lon = np.mean(lon[nv.flatten()].reshape(nv.shape),1)
                sub_idx = get_lat_lon_subset_idx(lon,lat,lonmin,latmin,lonmax,latmax)

            data_objs = variable

            # data needs to be [var1,var2] where var are 1D (nodes only, elevation and time already handled)
            data = []
            for do in data_objs:
                if len(do.shape) == 3: # time, elevation, node
                    data.append(do[t,z,:]) # TODO: does layer need to be a variable? would we ever handle a list of elevations?
                elif len(do.shape) == 2: # time, node (no elevation)
                    data.append(do[t,:])
                elif len(do.shape) == 1:
                    data.append(do[:]) # node (no time or elevation)
                else:
                    logger.info("Dimension Mismatch: data_obj.shape == {0} and time = {1}".format(data_obj.shape, time))
                    return blank_canvas(width, height)

            response = quiver_response(lon[sub_idx],
                                       lat[sub_idx],
                                       data[0][sub_idx],
                                       data[1][sub_idx],
                                       request)

            return response
                
        else:
            #don't know how to handle more than 2 variables
            logger.info("Cannot handle more than 2 variables per request.")
            canvas = blank_canvas(width, height)
            canvas.print_png(response)
            return response

        datasetnc.close()
        
    except:

        # log reason we dropped to this OLD code section, indicates some exception from pyugrid, lets just record why
        #exc_type, exc_value, exc_traceback = sys.exc_info()
        #logger.info("[IN C-GRID EXCEPT]: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))

#---------
        # lets get some support functions (probably copied verbatim from above and can be reduced to one) to index the target data
        def get_lat_lon_subset_idx(lon,lat,lonmin,latmin,lonmax,latmax,padding=0.50):
            """
            A function to return the indicies of lat, lon within a bounding box.
            """
            if lonmin > lonmax:
                lonmin = lonmin * -1.0 # TODO: this should solve USW integration sites at wide zoom, but is it best way?
            return np.asarray(np.where(
                (lat <= (latmax + padding)) & (lat >= (latmin - padding)) &
                (lon <= (lonmax + padding)) & (lon >= (lonmin - padding)),)).squeeze()

        def getvar(v, t, z, idx):
            '''
            v: netCDF4.Variable object
            t: time index
            z: vertical index
            /////idx: spatial indexes (list of tuples (i,j))
            idx: spatial indexes (list of list [[a],[b]])
            '''
            # non-UGRID (i,j based)
            if v is None:
                return None

            # first, subset by time/vertical
            # 3D: time/vertical/horizontal
            if len(v.shape) == 4:
                v = v[t,z,:,:]
            # 2D: time/horizontal
            elif len(v.shape) == 3:
                v = v[t,:,:]

            # v should be 2D (i,j) now, unique them so we're not duplicating data
            i = np.unique(idx[0])
            j = np.unique(idx[1])

            v = v[i,:]
            v = v[:,j]
            return v

#----------
        try:
            # Open topology cache file, and the actualy data endpoint
            topology = netCDF4.Dataset(os.path.join(settings.TOPOLOGY_PATH, dataset + '.nc'))
            datasetnc = netCDF4.Dataset(url, 'r')

            # SPATIAL SUBSET
            # load the lon and lat arrays
            lon = cf.get_by_standard_name(topology, 'longitude')[:]
            lat = cf.get_by_standard_name(topology, 'latitude')[:]

            # TODO: best way to subset this?
            sub_idx = get_lat_lon_subset_idx(lon, lat, lonmin, latmin, lonmax, latmax)

            #if no insersection with the field of view, return a transparent tile
            if len(sub_idx) == 0:
                logger.info("No intersection with in field of view, returning empty tile.")
                return blank_canvas(width, height);

            # scalar
            if len(variables) == 1:

                #now only accepting cf-standard names
                var = variables[0] # because it comes in as list, just using var for consistency with getFeatureInfo
                variable = cf.get_by_standard_name(datasetnc, var)

                if variable is None:
                    logger.warning('LAYERS {0} N/A'.format(var))
                    return blank_canvas(width, height) # was continue

                # subset lon/lat and the data (should be the same size)
                lon_subset = getvar(cf.get_by_standard_name(topology, 'longitude'), t, z, sub_idx)
                lat_subset = getvar(cf.get_by_standard_name(topology, 'latitude'), t, z, sub_idx)
                data_subset = getvar(variable, t, z, sub_idx)

                response = contourf_response(lon_subset,
                                             lat_subset,
                                             data_subset,
                                             request)

            # vector
            elif len(variables) == 2:

                variable = [cf.get_by_standard_name(datasetnc, v) for v in variables]

                # subset lon/lat and the data (should be the same size)
                lon_subset = getvar(cf.get_by_standard_name(topology, 'longitude'), t, z, sub_idx)
                lat_subset = getvar(cf.get_by_standard_name(topology, 'latitude'), t, z, sub_idx)
                
                u_subset = getvar(variable[0], t, z, sub_idx)
                v_subset = getvar(variable[1], t, z, sub_idx)

                response = quiver_response(lon_subset,
                                           lat_subset,
                                           u_subset,
                                           v_subset,
                                           request)

            # bad request, more than 2 vars (or none)
            else:
                #don't know how to handle more than 2 variables
                logger.info("Cannot handle more than 2 variables per request.")
                return blank_canvas(width, height)
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.info("[C-GRID ERROR]: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))

    return response
