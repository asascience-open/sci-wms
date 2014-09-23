"""
This is /sciwms/apps/wms/get_feature_info.py
"""
import os
import sys
import traceback
import logging
import bisect
import json
import multiprocessing
import datetime
from datetime import date
from collections import deque

from django.conf import settings
from django.http import HttpResponse
from django.core.exceptions import ObjectDoesNotExist

from .models import Dataset

try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

import numpy
import netCDF4

import pyugrid
from rtree import index as rindex

from . import wms_handler
from .matplotlib_handler import blank_canvas,\
     quiver_response, get_nearest_start_time, contourf_response
from ...util import cf, get_pyproj,\
      get_rtree_nodes_path, rtree_nodes_exists,\
      print_exception

output_path = os.path.join(settings.PROJECT_ROOT, 'logs', 'sciwms_wms.log')
# Set up Logger
logger = multiprocessing.get_logger()
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(output_path)
formatter = logging.Formatter(fmt='[%(asctime)s] - <<%(levelname)s>> - getFeatureInfo - |%(message)s|')
handler.setFormatter(formatter)
logger.addHandler(handler)


def getFeatureInfo(request, dataset):
    """
     /wms/GOM3/?ELEVATION=1&LAYERS=temp&FORMAT=image/png&TRANSPARENT=TRUE&STYLES=facets_average_jet_0_32_node_False&SERVICE=WMS&VERSION=1.1.1&REQUEST=GetFeatureInfo&SRS=EPSG:3857&BBOX=-7949675.196111,5078194.822174,-7934884.63114,5088628.476533&X=387&Y=196&INFO_FORMAT=text/csv&WIDTH=774&HEIGHT=546&QUERY_LAYERS=salinity&TIME=2012-08-14T00:00:00/2012-08-16T00:00:00
    """
    try:
        logger.info("IN getFeatureInfo!!!")
        X, Y = wms_handler.get_xy(request)
        logger.debug("x = {0}, y = {1}".format(X,Y))

        xmin, ymin, xmax, ymax = wms_handler.get_bbox(request)
        logger.debug("xmin = {0}, ymin = {1}, xmax = {2}, ymax = {3}".\
                     format(xmin, ymin, xmax, ymax))

        width, height = wms_handler.get_width_height(request)
        logger.debug("width = {0}, height = {1}".format(width, height))

        styles = request.GET["styles"].split(",")[0].split("_")
        logger.debug("styles = {0}".format(styles))

        QUERY_LAYERS = request.GET['query_layers'].split(",")
        logger.debug("QUERY_LAYERS = {0}".format(QUERY_LAYERS))

        elevation = wms_handler.get_elevation(request)
        logger.debug("elevation = {0}".format(elevation))

        mi = get_pyproj(request)
        # Find the gfi position as lat/lon, assumes 0,0 is ul corner of map

        # target longitude, target latitude
        tlon, tlat = mi(xmin+((xmax-xmin)*(X/width)),
                        ymax-((ymax-ymin)*(Y/height)),
                        inverse=True)

        logger.debug('tlon = {0}, tlat = {1}'.format(tlon,tlat))

        lonmin, latmin = mi(xmin, ymin, inverse=True)
        lonmax, latmax = mi(xmax, ymax, inverse=True)

        logger.debug('lonmin = {0}, latmin = {1}, lonmax = {2}, latmax = {3}'.\
                     format(lonmin, latmin, lonmax, latmax))
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.info("getFeatureInfo ERROR: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))

    # want data at (tlon,tlat)

    # outline
    # 1) use topology to get lat/lon values: this uses pyugrid for UGRID compliant datasets
    # 2) get index of "node" that is closest to the requested point
    #    NOTE: node is more meaningful in UGRID, but is also created for each grid point in structured grids


    ugrid = False # flag to track if UGRID file is found
    # ------------------------------------------------------------------------------------------------------------UGRID
    # pyugrid to handle UGRID topology
    try:
        logger.info("Trying to load pyugrid cache {0}".format(dataset))
        try:
            topology_path = os.path.join(settings.TOPOLOGY_PATH, dataset + '.nc')
        
            ug = pyugrid.UGrid.from_ncfile(topology_path)
        except:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.info("getFeatureInfo ERROR: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            
        logger.info("Loaded pyugrid cache")

        # UGRID variables
        lon = ug.nodes[:,0]
        lat = ug.nodes[:,1]
        nv  = ug.faces[:]

        # rindex, create if none exists yet
        try:
            nodes_path, idx_path, dat_path = get_rtree_nodes_path(dataset)
            # logger.debug("nodes_path = {0}".format(nodes_path))
            # logger.debug("idx_path = {0}".format(idx_path))
            # logger.debug("dat_path = {0}".format(dat_path))
            # logger.debug('os.path.exists(idx_path) is {0}'.format(os.path.exists(idx_path)))
            # logger.debug('os.path.exists(dat_path) is {0}'.format(os.path.exists(dat_path)))
            # logger.debug('rtree_nodes_exists(dataset) is {0}'.\
            #              format(rtree_nodes_exists(dataset)))
            
            tree = None
            if rtree_nodes_exists(dataset):
                    logger.info('UGRID node index found %s' % nodes_path)
                    tree = rindex.Index(nodes_path)
                    logger.info('UGRID node index loaded.')

                    print_exception(log=logger)
            else:
                def generator_nodes():
                    for i, c in enumerate(zip(lon, lat, lon, lat)):
                        yield(i, c, None)
                logger.info('UGRID indexing nodes %s' % idx_path)
                tree = rindex.Index(nodes_path, generator_nodes(), overwrite=True)
                logger.info('UGRID nodes indexed')

        except:
            logger.info("HERE")
            print_exception(log=logger)
            
        logger.debug('Searching for closest node/cell for tlat={0}, tlon={1}'.\
                     format(tlon,tlat))
        try:
            # find closest node or cell (only doing node for now)
            nindex = list(tree.nearest((tlon, tlat, tlon, tlat), 1, objects=True))[0]
            logger.debug('nearest index = {0}'.format(nindex))
            
            selected_longitude, selected_latitude = tuple(nindex.bbox[:2])
            logger.debug('selected_longitude = {0}, selected_latitude = {1}'.\
                         format(selected_longitude, selected_latitude))
            
            index = nindex.id # single value (node index)
            # tree.close()
        except:
            print_exception(log=logger)
            logger.info("there")
        finally:
            tree.close()
            logger.info("everywhere")
            
        logger.debug("Found closest node/cell @ index = {0}".format(index))
        
        # this is UGRID
        ugrid = True
    
    # ------------------------------------------------------------------------------------------------------------ Not pyUGRID
    except: # default to previous workflow for non UGRID
        # structured grids (where 'nodes' are the structured points)
        topology = netCDF4.Dataset(
            os.path.join(settings.TOPOLOGY_PATH, dataset + '.nc'))
        
        lats = topology.variables['lat'][:]
        lons = topology.variables['lon'][:]

        # rindex, create if none exists yet
        nodes_path = os.path.join(settings.TOPOLOGY_PATH, dataset + '_nodes')
        if os.path.exists(nodes_path+'.dat') and os.path.exists(nodes_path+'.idx'):
            tree = rindex.Index(nodes_path)
            logger.info('non-UGRID node index found %s' % nodes_path)
        else:
            def generator_nodes():
                c = -1
                for row in range(lons.shape[0]):
                    for col in range(lons.shape[1]):
                        coord = (lons[row, col], lats[row, col], lons[row, col], lats[row, col],)
                        c += 1
                        yield(c, coord, ((row,), (col,)))
            logger.info('non-UGRID indexing nodes %s' % nodes_path)
            tree = rindex.Index(nodes_path, generator_nodes(), overwrite=True)
            logger.info('non-UGRID nodes indexed')

        # find closest node or cell (only doing node for now)
        nindex = list(tree.nearest((tlon, tlat, tlon, tlat), 1, objects=True))[0] # returns generator > cast to list and get [0] value
        # why are lat/lon 3d? eg. why using the [0] index in next line for both lats and lons
        logger.info('shape of lons: {0}'.format(lons.shape))
        logger.info('shape of lats: {0}'.format(lats.shape))
        
        selected_longitude, selected_latitude = lons[nindex.object[0], nindex.object[1]][0], lats[nindex.object[0], nindex.object[1]][0]
        #index = nindex.object # tuple ((row,),(col,))
        index = (nindex.object[0][0],nindex.object[1][0]) # tuple(row,col) from that nasty ((row,),(col,)) returned object
        logger.info('index: {0}'.format(index))
        tree.close()
        #index = numpy.asarray(index) # array([[row],[col]])
        topology.close()

    # nothing UGRID related below

    try:
        url = Dataset.objects.get(name=dataset).path()
    except:
        logger.error("Couldn't find {0} in database".format(dataset))
        print_exception(log=logger)
        
    datasetnc = netCDF4.Dataset(url)
    logger.debug('loaded datasetnc')

    try:
        TIME = request.GET["time"]
        if TIME == "":
            now = date.today().isoformat()
            TIME = now + "T00:00:00"
    except:
        now = date.today().isoformat()
        TIME = now + "T00:00:00"
    TIMES = TIME.split("/")
    for i in range(len(TIMES)):
        TIMES[i] = TIMES[i].replace("Z", "")
        if len(TIMES[i]) == 16:
            TIMES[i] = TIMES[i] + ":00"
        elif len(TIMES[i]) == 13:
            TIMES[i] = TIMES[i] + ":00:00"
        elif len(TIMES[i]) == 10:
            TIMES[i] = TIMES[i] + "T00:00:00"
    if len(TIMES) > 1:
        datestart = datetime.datetime.strptime(TIMES[0], "%Y-%m-%dT%H:%M:%S" )
        dateend = datetime.datetime.strptime(TIMES[1], "%Y-%m-%dT%H:%M:%S" )
        times = datasetnc.variables['time'][:]
        time_units = datasetnc.variables['time'].units
        datestart = round(netCDF4.date2num(datestart, units=time_units))
        dateend = round(netCDF4.date2num(dateend, units=time_units))
        time1 = bisect.bisect_right(times, datestart) - 1
        time2 = bisect.bisect_right(times, dateend) - 1
        if time1 == -1:
            time1 = 0
        if time2 == -1:
            time2 = len(times)
        time = range(time1, time2)
        if len(time) < 1:
            time = [len(times) - 1]
    else:
        datestart = datetime.datetime.strptime(TIMES[0], "%Y-%m-%dT%H:%M:%S" )
        times = datasetnc.variables['time'][:]
        time_units = datasetnc.variables['time'].units
        datestart = round(netCDF4.date2num(datestart, units=time_units))
        time1 = bisect.bisect_right(times, datestart) - 1
        if time1 == -1:
            time = [0]
        else:
            time = [time1-1]


    def getvar(v, t, z, i):
        '''
        v: netCDF4.Variable object
        t: time index(es) - ONLY index that can be > 1
        z: vertical index (eg. elevation/z)
        i: spatial index (closest point) THIS MUST BE ONE, tuple if i/j
        '''
        # TODO: protect against i(ndex) being more than 2, should be node(1 value) or i/j(2 tuple)
        # non-UGRID (i,j based)
        if isinstance(i, tuple):
            # 3D: time/vertical/horizontal
            if len(v.shape) == 4:
                return v[t,z,i[0],i[1]]
            # 2D: time/horizontal
            elif len(v.shape) == 3:
                return v[t,i[0],i[1]]
            # 1D: horizontal (independent of time)
            elif len(v.shape) == 2:
                return [v[i[0],i[1]]] # return expects list
        # UGRID (node based)
        else:
            # 3D: time/vertical/horizontal
            if len(v.shape) == 3:
                return v[t,z,i]
            # 2D: time/horizontal
            elif len(v.shape) == 2:
                return v[t,i]
            # 1D: horizontal (independent of time)
            elif len(v.shape) == 1:
                return [v[i]] # return expects list
    try:
        # get values for requested QUERY_LAYERS
        varis = deque()
        # try to get 'time' by standard_name field
        time_variable = cf.get_by_standard_name(datasetnc, 'time')
        # if couldn't find by standard_name, try 'time'
        if time_variable is None:
            time_variable = datasetnc.variables['time']
        # TODO: handle not finding time dimension
        varis.append(time_variable[time]) # adds time as first element (in NetCDF format, converted later) [time] should be [tindex] or something obviously an index
        for var in QUERY_LAYERS:
            # map from QUERY_LAYERS name (AKA UI name) to CF standard_name
            # v = cf.map.get(var, None)
            # if v == None:
            #     logger.warning('requested QUERY_LAYER %s, no map exists to CF standard_name' % var)
            #     continue
            variable = cf.get_by_standard_name(datasetnc, var)
            try:
                units = variable.units
            except:
                units = ""
            values = getvar(variable, time, elevation, index)
            logger.info('appending ({0},{1},{2})'.format(var,units,":"))
            varis.append((var, units, values))
    except:
        print_exception(log=logger)

    # convert time to Python datetime object
    varis[0] = netCDF4.num2date(varis[0], units=time_units)

    # restructure the array
    X = numpy.asarray([var for var in varis])
    X = numpy.transpose(X)

    # return based on INFO_FORMAT TODO: BM needs to update this
    if request.GET["INFO_FORMAT"].lower() == "image/png":
        response = HttpResponse("Response MIME Type image/png is currently unavailable")
        '''
        response = HttpResponse(content_type=request.GET["INFO_FORMAT"].lower())
        from matplotlib.figure import Figure
        fig = Figure()
        ax = fig.add_subplot(111)
        ax.plot(varis[0], varis[1])  # Actually make line plot
        tdelta = varis[0][-1]-varis[0][0]
        if tdelta.total_seconds()/3600. <= 36:
            if tdelta.total_seconds()/3600. <= 12:
                interval = 2
            elif tdelta.total_seconds()/3600. <= 24:
                interval = 4
            elif tdelta.total_seconds()/3600. <= 36:
                interval = 6
            ax.xaxis.set_minor_locator(matplotlib.dates.HourLocator())
            ax.xaxis.set_major_locator(matplotlib.dates.HourLocator(interval=interval))
            ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%Y/%m/%d\n%H:%M'))
        if tdelta.total_seconds()/3600. <= 96:
            #if tdelta.total_seconds()/3600. <= 48:
            interval = 12
            #elif tdelta.total_seconds()/3600. <= 60:
            #    interval = 14
            #elif tdelta.total_seconds()/3600. <= 72:
            #    interval = 16
            ax.xaxis.set_minor_locator(matplotlib.dates.HourLocator())
            ax.xaxis.set_major_locator(matplotlib.dates.HourLocator(interval=interval))
            ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%Y/%m/%d\n%H:%M'))
        if tdelta.total_seconds()/3600. <= 120:
            interval = 1
            ax.xaxis.set_minor_locator(matplotlib.dates.HourLocator())
            ax.xaxis.set_major_locator(matplotlib.dates.DayLocator(interval=interval))
            ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%Y/%m/%d'))
        if tdelta.total_seconds()/3600. <= 240:
            interval = 2
            ax.xaxis.set_minor_locator(matplotlib.dates.HourLocator())
            ax.xaxis.set_major_locator(matplotlib.dates.DayLocator(interval=interval))
            ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%Y/%m/%d'))
        ax.grid(True)
        ax.set_ylabel(QUERY_LAYERS[0] + "(" + units + ")")
        canvas = FigureCanvasAgg(fig)
        canvas.print_png(response)
        '''
    elif request.GET["INFO_FORMAT"].lower() == "application/json":
        import json
        response = HttpResponse("Response MIME Type application/json not supported at this time")
    elif request.GET["INFO_FORMAT"].lower() == "text/javascript":
        """
        http://docs.geoserver.org/latest/en/user/services/wms/reference.html#getfeatureinfo
        """
        import json
        # get callback value if specified
        callback = request.GET.get("callback", "parseResponse")
        # top level JSON return values [type,geometry]
        d = {}
        d["type"] = "Feature"
        d["geometry"] = { "type" : "Point", "coordinates" : [float(selected_longitude), float(selected_latitude)] }
        # build 'properties' value of return
        properties = {}
        properties['time'] = {'units':'iso', 'values':[t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in varis[0]]}
        properties['latitude'] = {'units':'degrees_north', 'values':float(selected_latitude)}
        properties['longitude'] = {'units':'degrees_east', 'values':float(selected_longitude)}
        # varis are tuple(name,unit,data)
        for v in [varis[i] for i in range(1,len(varis))]: # because deque was used and first is time, ugh, http://stackoverflow.com/questions/10003143/how-to-slice-a-deque
            name = v[0]
            units = v[1]
            values = [] # output as floats
            for value in v[2]:
                if numpy.isnan(value):
                    values.append(float('nan'))
                else:
                    values.append(float(value))
            properties[name] = {'units':units, 'values':values}
        d['properties'] = properties
        # output string to return
        output = callback + '(' + json.dumps(d, indent=4, separators=(',', ': '), allow_nan=True) + ')'
        # HttpResponse
        response = HttpResponse()
        response.write(output)
    elif request.GET["INFO_FORMAT"].lower() == "text/csv":
        import csv
        buffer = StringIO()
        c = csv.writer(buffer)
        header = ["time"]
        header.append("latitude[degrees_north]")
        header.append("longitude[degrees_east]")
        for v in [varis[i] for i in range(1,len(varis))]: # because deque was used and first is time, ugh, http://stackoverflow.com/questions/10003143/how-to-slice-a-deque
            name = v[0]
            units = v[1]
            header.append(name+'['+units+']')
        c.writerow(header)
        # each line (time and vars should be same length)
        for i, t in enumerate(varis[0]):
            # row array is the values of the line, the V in CSV
            row = [t.strftime("%Y-%m-%dT%H:%M:%SZ")]
            row.append(selected_latitude)
            row.append(selected_longitude)
            for k in range(1, len(varis)):
                values = varis[k][2]
                if type(values)==numpy.ndarray or type(values)==numpy.ma.core.MaskedArray:
                    try:
                        row.append(values[i])
                    except:
                        row.append(values) # triggered if scalar?
                # if variable not changing with type, like bathy
                else:
                    row.append(values)
            c.writerow(row)
        dat = buffer.getvalue()
        buffer.close()
        response = HttpResponse()
        response.write(dat)
    else:
        response = HttpResponse("Response MIME Type %s not supported at this time" % request.GET["INFO_FORMAT"].lower())
    datasetnc.close()
    return response
