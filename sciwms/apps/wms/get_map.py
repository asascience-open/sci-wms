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
from ...libs.data.ugrid import Ugrid

import rtree
from ...libs.data.caching import FastRtree


output_path = os.path.join(settings.PROJECT_ROOT, 'logs', 'sciwms_wms.log')
logger = multiprocessing.get_logger()

def getMap(request, dataset):
    """
    the meat and bones of getMap
    """
    response = HttpResponse(content_type='image/png')

    logger.debug("getMap request.GET = {0}".format(request.GET))
    logger.debug("dataset = {0}".format(dataset))

    # direct the service to the dataset
    url = dbDataset.objects.get(name=dataset).path()

    datestart, dateend = wms_handler.get_date_start_end(request)
    
    logger.debug("datestart = {0}, dateend = {1}".format(datestart, dateend))
    # BM: buyer beware, this is actually WMS 'ELEVATION', AKA z coordinate, NOT WMS 'LAYERS'
    # TODO: find closest vertical index, for now, just zero

    logger.info("HERE")
    try:
        time = get_nearest_start_time(datasetnc, datestart)
    except:
        time = 0
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.info("Dataset doesn't contain temporal dimension: "
                    + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    logger.info("time = {0}".format(time))

    logger.info("THERE")
    t = time
    layer = [0]
    # z = layer[0]
    z = wms_handler.get_elevation(request)

    logger.info("t = {0}, z = {1}".format(t,z))
    

    # variables = request.GET["LAYERS"].split(",")# NOTE: this 'variables' is actually WMS LAYERS, see wms_handler
    variables = wms_handler.get_layers(request)
    logger.info("variables = {0}".format(variables))

    #THIS IS IN PROJECTED COORDINATES DON'T CALL lat/lon ITS DAMN CONFUSING.
    xmin, ymin, xmax, ymax = wms_handler.get_bbox(request)
    
    # lonmin, latmin, lonmax, latmax = wms_handler.get_bbox(request)
    logger.debug("bbox in projection crs = {0}".format([xmin, ymin, xmax, ymax]))

    width, height = wms_handler.get_width_height(request)
    logger.debug("width = {0}, height = {1}".format(width,height))

    # Get the box coordinates from webmercator to proper lat/lon for grid subsetting
    # mi = pyproj.Proj("+proj=merc +lon_0=0 +k=1 +x_0=0 +y_0=0 +a=6378137 +b=6378137 +units=m +no_defs ")

    #CAN PROBABLY GET RID OF THIS JUST KEEPING FOR NOW FOR BACKWARDS COMPAT.
    #PROJECTS FROM PROJECTED COORDINATES TO LAT/LON
    proj = get_pyproj(request)

    lonmin, latmin = proj(xmin, ymin, inverse=True)
    lonmax, latmax = proj(xmax, ymax, inverse=True)
    logger.debug("lat/lon bbox: {0}, {1}, {2}, {3}".format(lonmin,latmin,lonmax,latmax))

    try:
        from .matplotlib_handler import get_lat_lon_subset_idx, get_nv_subset_idx, get_nearest_start_time
        import matplotlib.tri as Tri
        
        logger.info("Trying to load pyugrid cache {0}".format(dataset))
        topology_path = os.path.join(settings.TOPOLOGY_PATH, dataset + '.nc')
        ug = pyugrid.UGrid.from_ncfile(topology_path)
        logger.info("Loaded pyugrid cache")    

        logger.info("getMap Computing Triangulation Subset")
        #check that this is correct lat/lon NOTE: below we do this again IF UGRID.location = 'face'
        lon = ug.nodes[:,0]
        lat = ug.nodes[:,1]
        
        sub_idx = get_lat_lon_subset_idx(lon,lat,lonmin,latmin,lonmax,latmax)
        nv  = ug.faces[:]

        nv_subset_idx = get_nv_subset_idx(nv, sub_idx)

        logger.info("Found {0} triangles in view".format(len(nv_subset_idx)))

        #if no traingles insersect the field of view
        #return a transparent tile
        if (len(sub_idx) == 0) or (len(nv_subset_idx) == 0):
            logger.info("No triangles in field of view, returning empty tile.")
            canvas = blank_canvas(width,height)
            canvas.print_png(response)
            return response

        triang_subset = Tri.Triangulation(lon,lat,triangles=nv[nv_subset_idx])
        
        logger.info("getMap Computing Triangulation Subset Complete.")

        datasetnc = netCDF4.Dataset(url,'r')
        
        time = get_nearest_start_time(datasetnc, datestart)
            
        logger.info("time = {0}".format(time))
        
        # some short names for indexes
        t = time
        z = layer[0]

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

            logger.info("len(variables) == 1")

            v = variables[0] # because it comes in as list, just using var for consistency with getFeatureInfo
            # get Variable using CF standard_name attribute
            # v = cf.map.get(var, None)
            if v == None:
                logger.warning('requested LAYERS %s, no map exists to CF standard_name' % var)
                canvas = blank_canvas(width, height)
                canvas.print_png(response)
                return response
            
            variable = cf.get_by_standard_name(datasetnc, v)

            # logger.info('getMap retrieving LAYER %s with standard_name %s' % (var, v['standard_name']))
            logger.info('getMap retrieving Layer {0}'.format(v))

            #data_obj = datasetnc.variables[variables[0]]
            data_obj = variable

            #I find its faster to grab all data then to grab only
            #subindicies from server
            if (len(data_obj.shape) == 3) and (time != None):
                logger.info("getMap slicing time {0} and z {1}".format(time,z))
                data = data_obj[t,z,:]
            elif (len(data_obj.shape) == 2) and (time != None):
                logger.info("getMap slicing time {0}".format(time))
                data = data_obj[t,:]
            elif len(data_obj.shape) == 1:
                logger.info("getMap variable has no time dimension.")
                data = data_obj[:]
            else:
                logger.info("Dimension Mismatch: data_obj.shape == {0} and time = {1}".format(data_obj.shape, time))
                canvas = blank_canvas(width, height)
                canvas.print_png(response)
                return response
            
            logger.info("getMap finished retrieving variable {0}, serving tricontourf response".format(variables)) # TODO this logger statement (variables is list?)
            import matplotlib_handler
            # canvas = matplotlib_handler.tricontourf_canvas(topology, datasetnc, request)
            try:
                from . matplotlib_handler import tricontourf_response
                # response = tricontourf_response(triang_subset, data, xmin, ymin, xmax, ymax, width, height, request)
                response = tricontourf_response(triang_subset, data, request)
            except:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logger.info("getMap import error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            # canvas.print_png(response)
            return response

        # vector
        elif len(variables) == 2:

            logger.info("len(variables) == 2")
            logger.info("variables = {0}".format(variables))
                
            # variable = map(lambda x: cf.get_by_standard_name(datasetnc, x['standard_name']), variables)

            variable = [cf.get_by_standard_name(datasetnc, v) for v in variables]
            logger.info("variable = {0}".format(variable))

            if None in variable:
                logger.warning('variable not found for at least these'.format(variables))
                canvas = blank_canvas(width, height)
                canvas.print_png(response)
                return response
                # return blank_canvas(width, height) # was continue

            logger.info("getMap retrieving variables {0}".format(variables))
            logger.info("time = {0}".format(time))

            # UGRID data has momentum (u,v) either on node (AKA vertices, eg. ADCIRC) or face (AKA triangle, eg. FVCOM/SELFE)
            #     check the location attribute of the UGRID variable to determine which lon/lat to use (if face, need a different set)
            location = set([v.__dict__.get('location', None) for v in variable])
            if len(location) > 1:
                logger.info("UGRID vector component variables require same 'location' attribute")
                canvas = blank_canvas(width, height)
                canvas.print_png(response)
                return response
                # return blank_canvas(width, height)
            
            # hacky to do here, but in rush and it doesn't appear that replacing these within this scope will cause any problems
            if list(location)[0] == 'face':
                lat = np.mean(lat[nv.flatten()].reshape(nv.shape),1)
                lon = np.mean(lon[nv.flatten()].reshape(nv.shape),1)
                sub_idx = get_lat_lon_subset_idx(lon,lat,lonmin,latmin,lonmax,latmax)


            #data_objs = [datasetnc.variables[v] for v in variables]
            data_objs = variable

            # data needs to be [var1,var2] where var are 1D (nodes only, elevation and time already handled)
            data = []
            for do in data_objs:
                logger.info("do.shape = {0}".format(do.shape))
                logger.info("len(do.shape) = {0}".format(len(do.shape)))
                logger.info("t = {0}".format(t))
                logger.info("z = {0}".format(z))
                if len(do.shape) == 3: # time, elevation, node
                    #logger.info('t,z,{0},{1},{2}'.format(t,z,do[t,z,:].shape))
                    data.append(do[t,z,:]) # TODO: does layer need to be a variable? would we ever handle a list of elevations?
                elif len(do.shape) == 2: # time, node (no elevation)
                    data.append(do[t,:])
                elif len(do.shape) == 1:
                    data.append(do[:]) # node (no time or elevation)
                else:
                    logger.info("Dimension Mismatch: data_obj.shape == {0} and time = {1}".format(data_obj.shape, time))
                    return blank_canvas(width, height)

            logger.info("len(data) = {0}".format(len(data)))
            logger.info("data[0].shape = {0}".format(data[0].shape))
            logger.info("data[1].shape = {0}".format(data[1].shape))

            logger.debug("np.max(data[0]) = {0}".format(np.max(data[0])))
            
            response = quiver_response(lon[sub_idx],
                                       lat[sub_idx],
                                       data[0][sub_idx],
                                       data[1][sub_idx],
                                       request)

            return response
                
        else:
            #don't know how to handle more than 2 variables
            logger.info("Cannot handle more than 2 variables per request.")
            # return blank_canvas(width, height)
            canvas = blank_canvas(width, height)
            canvas.print_png(response)
            return response

        # topology.close()
        datasetnc.close()
        
    except:

        # log reason we dropped to this OLD code section, indicates some exception from pyugrid, lets just record why
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.info("[IN C-GRID EXCEPT]: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))

#---------
        # lets get some support functions (probably copied verbatim from above and can be reduced to one) to index the target data
        def get_lat_lon_subset_idx(lon,lat,lonmin,latmin,lonmax,latmax,padding=0.18):
            """
            A function to return the indicies of lat, lon within a bounding box.
            """
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
            gridtype = topology.grid  # Grid type found in topology file (False is UGRID)
            logger.info("gridtype: " + gridtype)


            # SPATIAL SUBSET
            # load the lon and lat arrays
            lon = topology.variables['lon'][:]
            lat = topology.variables['lat'][:]

            # TODO: best way to subset this?
            # get the subset (returns array of array [[i,i,...],[j,j,...]]
            sub_idx = get_lat_lon_subset_idx(lon, lat, lonmin, latmin, lonmax, latmax)
            # zip into a list of tuples (i,j)
            #sub_idx = zip(*sub_idx)

            #if no insersection with the field of view, return a transparent tile
            if len(sub_idx) == 0:
                logger.info("No intersection with in field of view, returning empty tile.")
                return blank_canvas(width, height);

            logger.debug("[C-GRID] t = {0}, z = {0}".format(t,z))

            # logger.info('dataset.variables[\'time\'].shape = {0}'.format(datasetnc.variables['time'].shape))
            # scalar
            if len(variables) == 1:

                logger.info("[C-GRID] len(variables) == 1")

                #now only accepting cf-standard names
                var = variables[0] # because it comes in as list, just using var for consistency with getFeatureInfo
                variable = cf.get_by_standard_name(datasetnc, var)

                if variable is None:
                    logger.warning('LAYERS {0} N/A'.format(var))
                    return blank_canvas(width, height) # was continue

                logger.info('getMap retrieving LAYER {0}'.format(var))

                # subset lon/lat and the data (should be the same size)
                lon_subset = getvar(cf.get_by_standard_name(datasetnc, 'longitude'), t, z, sub_idx)
                lat_subset = getvar(cf.get_by_standard_name(datasetnc, 'latitude'), t, z, sub_idx)
                data_subset = getvar(variable, t, z, sub_idx)

                logger.info("lon_subset.shape = {0}".format(lon_subset.shape))
                logger.info("lat_subset.shape = {0}".format(lat_subset.shape))
                logger.info("data_subset.shape = {0}".format(data_subset.shape))

                logger.info("getMap [non-UGRID] finished retrieving variable {0}, serving contourf response".format(variables)) # TODO this logger statement (variables is list?)

                response = contourf_response(lon_subset,
                                             lat_subset,
                                             data_subset,
                                             request)

            # vector
            elif len(variables) == 2:

                logger.info("[C-GRID] len(variables) == 2")

                variable = [cf.get_by_standard_name(datasetnc, v) for v in variables]



                # subset lon/lat and the data (should be the same size)
                lon_subset = getvar(cf.get_by_standard_name(datasetnc, 'longitude'), t, z, sub_idx)
                lat_subset = getvar(cf.get_by_standard_name(datasetnc, 'latitude'), t, z, sub_idx)
                
                logger.info("getMap retrieving variables {0}".format(variables))
                u_subset = getvar(variable[0], t, z, sub_idx)
                v_subset = getvar(variable[1], t, z, sub_idx)

                logger.info("lon_subset.shape = {0}".format(lon_subset.shape))
                logger.info("lat_subset.shape = {0}".format(lat_subset.shape))
                logger.info("u_subset.shape = {0}".format(u_subset.shape))
                logger.info("v_subset.shape = {0}".format(v_subset.shape))

                logger.info("getMap [non-UGRID] finished retrieving variable {0}, serving quiver response".format(variables)) # TODO this logger statement (variables is list?)
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

    # gc.collect()

    return response
