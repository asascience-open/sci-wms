"""
this is sciwms.apps.wms.getMapUtils

Utilities for rendering WMS getMap requests
"""
import bisect
import datetime
import multiprocessing
import sys
import traceback

import matplotlib
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from . import wms_handler
from ...util.cf import get_by_standard_name

import numpy as np

import netCDF4

logger = multiprocessing.get_logger()

def get_lat_lon_subset_idx(lon,lat,lonmin,latmin,lonmax,latmax,padding=0.18):
    """
    A function to return the indicies of lat, lon within a bounding box.
    Padding is leftover from old sciwms code, I believe it was to include triangles
    lying just outside the region of interest so that there are no holes in the
    rendered image.
    """
    return np.asarray(np.where(
        (lat <= (latmax + padding)) & (lat >= (latmin - padding)) &
        (lon <= (lonmax + padding)) & (lon >= (lonmin - padding)),)).squeeze()

def get_nv_subset_idx(nv, sub_idx):
    """
    Return row indicies into the nv data structure which have indicies
    inside the bounding box defined by get_lat_lon_subset_idx
    """
    return np.asarray(np.where(np.all(np.in1d(nv,sub_idx).reshape(nv.shape),1))).squeeze()

def get_nearest_start_time(nc,datestart):
    time = None
    logger.debug("in get_nearest_time")
    try:
        logger.debug('foo')
        # times = nc.variables['time'][:]
        time_obj = get_by_standard_name(nc,'time')
        times = None
        if time_obj:
            times = time_obj[:]
        else:
            logger.debug("No times available.")
            return 0
    
        datestart = datetime.datetime.strptime(datestart, "%Y-%m-%dT%H:%M:%S" )

        # datetime obj --> netcdf datenum
        cal = time_obj.__dict__.get('calendar','gregorian')
        units = time_obj.__dict__.get('units')
        datestart = round(netCDF4.date2num(datestart, units=units, calendar=cal))

        #bisect_right returns the index that would maintain sorted order if
        #the element (in this case datestart) was inserted to the right of an element
        time = bisect.bisect_right(times,datestart)
        

        #goal is to find closest time index, or do we always use the "one before" or "one after"?            
        #This mod will get the nearest element by checking the one after vs. the one before
        if time == len(times):
            time -= 1
        elif time != 0:
            time = time if abs(times[time]-datestart) < abs(times[time-1]-datestart) else time-1
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.info("ERROR: get_nearest_start_time:: "
                    + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    finally:
        del times
    

    return time

def blank_canvas(width, height, dpi=5):
    """
    return a transparent (blank) response
    used for tiles with no intersection with the current view or for some other error.
    """
    fig = Figure(dpi=dpi, facecolor='none', edgecolor='none')
    fig.set_alpha(0)
    ax = fig.add_axes([0, 0, 1, 1])
    fig.set_figheight(height/dpi)
    fig.set_figwidth(width/dpi)
    ax.set_frame_on(False)
    ax.set_clip_on(False)
    ax.set_position([0, 0, 1, 1])
    canvas = FigureCanvasAgg(fig)
    return canvas

def tricontourf_canvas(triang_subset,
                       data,
                       lonmin,
                       latmin,
                       lonmax,
                       latmax,
                       width,
                       height,
                       dpi=80.0,
                       nlvls = 15):
    pass

def tricontourf_canvas(topology, datasetnc, request):
    """
    topology - netcdf topology object
    dataset - netcdf dataset object
    request - original http request
    """
    import wms_handler
    from sciwms.util import get_pyproj

    logger.debug("In matplotlib_handler.tricontourf_canvas")
    
    xmin, ymin, xmax, ymax = wms_handler.get_bbox(request)
    logger.debug("bbox (crs) = {0}".format([xmin, ymin, xmax, ymax]))

    proj = get_pyproj(request)
    lonmin, latmin = proj(xmin, ymin, inverse=True)
    lonmax, latmax = porj(xmax, ymax, inverse=True)

    logger.debug("bbox (lat/lon) = {0}".format([lonmin,latmin,lonmax,latmax]))

    #compute triangular subset
    lon = topology.nodes[:,0]
    lat = topology.nodes[:,1]
    latlon_sub_idx = get_lat_lon_subset_idx(topology.nodes[:,0], topology[:,1], lonmin, latmin, lonmax, latmax)

    nv_sub_idx = get_nv_subset_idx(topology.faces[:], sub_idx)

def tricontourf_response(triang_subset,
                         data,
                         request,
                         dpi=80.0,
                         nlvls = 15):
    """
    triang_subset is a matplotlib.Tri object in lat/lon units (will be converted to projected coordinates)
    xmin, ymin, xmax, ymax is the bounding pox of the plot in PROJETED COORDINATES!!!
    request is the original getMap request object
    """
    from django.http import HttpResponse
    from sciwms.util import get_pyproj

    xmin, ymin, xmax, ymax = wms_handler.get_bbox(request)
    width, height = wms_handler.get_width_height(request)
    
    colormap = wms_handler.get_colormap(request)
    logger.debug("colormap = {0}".format(colormap))
    
    cmin, cmax = wms_handler.get_climits(request)
    logger.debug("cmin = {0}, cmax = {1}".format(cmin, cmax))
    
    clvls = wms_handler.get_clvls(request)
    logger.debug("clvls = {0}".format(clvls))

    proj = get_pyproj(request)
    
    logger.debug("Projecting topology.")
    triang_subset.x, triang_subset.y = proj(triang_subset.x, triang_subset.y)
    logger.debug("Done projecting topology.")

    fig = Figure(dpi=dpi, facecolor='none', edgecolor='none')
    fig.set_alpha(0)
    fig.set_figheight(height/dpi)
    fig.set_figwidth(width/dpi)

    ax = fig.add_axes([0., 0., 1., 1.], xticks=[], yticks=[])
    ax.set_axis_off()

    lvls = np.linspace(data.min(), data.max(), int(clvls))
    # lvls = np.linspace(float(cmin), float(cmax), int(clvls))
    logger.debug("lvls = {0}".format(lvls))
    ax.tricontourf(triang_subset, data, levels = lvls, cmap=colormap)

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)

    ax.set_frame_on(False)
    ax.set_clip_on(False)
    ax.set_position([0., 0., 1., 1.])

    plt.axis('off')

    canvas = FigureCanvasAgg(fig)
    response = HttpResponse(content_type='image/png')
    canvas.print_png(response)
    return response

def quiver_response(lon,
                    lat,
                    dx,
                    dy,
                    request,
                    unit_vectors=True,
                    dpi=80):
    
    logger.debug("Rendering ugrid quiver response.")
    from django.http import HttpResponse
    from sciwms.util import get_pyproj

    xmin, ymin, xmax, ymax = wms_handler.get_bbox(request)
    width, height = wms_handler.get_width_height(request)
    
    colormap = wms_handler.get_colormap(request)
    logger.debug("colormap = {0}".format(colormap))

    proj = get_pyproj(request)
    
    fig = Figure(dpi=dpi, facecolor='none', edgecolor='none')
    fig.set_alpha(0)
    fig.set_figheight(height/dpi)
    fig.set_figwidth(width/dpi)

    ax = fig.add_axes([0., 0., 1., 1.], xticks=[], yticks=[])
    ax.set_axis_off()

    logger.debug("Projecting ugrid lat/lon.")
    x, y = proj(lon, lat)
    logger.debug("Done projecting ugrid lat/lon.")

    #plot unit vectors
    if unit_vectors:
        mags = np.sqrt(dx**2 + dy**2)
        logger.debug("mags.max() = {0}".format(mags.max()))
        logger.debug("mags = {0}".format(mags[100:150]))

        ax.quiver(x, y, dx/mags, dy/mags, mags, cmap=colormap)
    else:
        ax.quiver(x, y, dx, dy, cmap=colormap)

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_frame_on(False)
    ax.set_clip_on(False)
    ax.set_position([0., 0., 1., 1.])

    logger.debug("finished rendering ugrid quiver.")

    canvas = FigureCanvasAgg(fig)
    response = HttpResponse(content_type='image/png')
    canvas.print_png(response)
    return response
    

def layered_quiver_response(lon, lat, dx, dy, sub_idx, triang_subset, lonmin, latmin, lonmax, latmax, width, height, dpi=80, nlvls=20):
    logger.info("In layered_quiver_response")
    fig = Figure(dpi=dpi, facecolor='none', edgecolor='none')
    fig.set_alpha(0)
    fig.set_figheight(height/dpi)
    fig.set_figwidth(width/dpi)
    projection = request.GET["projection"]
    m = Basemap(llcrnrlon=lonmin, llcrnrlat=latmin,
                urcrnrlon=lonmax, urcrnrlat=latmax, projection=projection,
                resolution=None,
                lat_ts = 0.0,
                suppress_ticks=True)
    m.ax = fig.add_axes([0, 0, 1, 1], xticks=[], yticks=[])

    mags = np.sqrt(dx**2 + dy**2)
    lvls = np.linspace(mags.min(), mags.max(), nlvls)

    m.ax.tricontourf(triang_subset, mags, levels=lvls)

    logger.info("tricontourf done.")

    m.ax.quiver(lon,lat,dx/mags,dy/mags)
    logger.info("quiver done.")

    m.ax.set_xlim(lonmin, lonmax)
    m.ax.set_ylim(latmin, latmax)
    m.ax.set_frame_on(False)
    m.ax.set_clip_on(False)
    m.ax.set_position([0, 0, 1, 1])
    canvas = FigureCanvasAgg(fig)
    response = HttpResponse(content_type='image/png')
    canvas.print_png(response)
    return response
