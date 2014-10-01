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

from django.conf import settings
from django.http import HttpResponse

from . import wms_handler
from ...util.cf import get_by_standard_name
from ...util import get_pyproj

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
    try:
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
    latlon_sub_idx = get_lat_lon_subset_idx(topology.nodes[:,0],
                                            topology[:,1],
                                            lonmin,
                                            latmin,
                                            lonmax,
                                            latmax)

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

    try:
        data[data>cmax] = cmax
        data[data<cmin] = cmin
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.info("tricontourf_response error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    
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

    lvls = np.linspace(float(cmin), float(cmax), int(clvls))
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
                    unit_vectors=False,
                    dpi=80):
    
    logger.debug("Rendering ugrid quiver response.")
    from django.http import HttpResponse
    from sciwms.util import get_pyproj

    xmin, ymin, xmax, ymax = wms_handler.get_bbox(request)
    width, height = wms_handler.get_width_height(request)
    
    colormap = wms_handler.get_colormap(request)
    logger.debug("colormap = {0}".format(colormap))

    climits = wms_handler.get_climits(request)

    cmax = 1.
    cmin = 0.
    
    if len(climits) == 2:
        logger.debug("cmin = {0}, cmax = {1}".format(*climits))
        cmin, cmax = climits
    else:
        logger.debug("No climits, default cmax to 1.0")

    # cmax = 10.
    logger.debug("cmin = {0}, cmax = {1}".format(cmin, cmax))

    proj = get_pyproj(request)

    logger.debug("Projecting ugrid lat/lon.")
    x, y = proj(lon, lat)
    logger.debug("Done projecting ugrid lat/lon.")
    
    fig = Figure(dpi=dpi, facecolor='none', edgecolor='none')
    fig.set_alpha(0)
    fig.set_figheight(height/dpi)
    fig.set_figwidth(width/dpi)

    ax = fig.add_axes([0., 0., 1., 1.], xticks=[], yticks=[])
    ax.set_axis_off()
    
    
    
    #scale to cmin - cmax
    # dx = cmin + dx*(cmax-cmin)
    # dy = cmin + dy*(cmax-cmin)
    mags = np.sqrt(dx**2 + dy**2)
    # mags[mags>cmax] = cmax

    import matplotlib as mpl
    cmap = mpl.cm.get_cmap(colormap)
    bounds = np.linspace(cmin, cmax, 15)
    norm = mpl.colors.BoundaryNorm(bounds, cmap.N)

    if settings.DEBUG==True:
        logger.debug("mags.shape = {0}".format(mags.shape))
        logger.debug("mags.max() = {0}".format(mags.max()))
        logger.debug("mags.min() = {0}".format(mags.min()))

    #plot unit vectors
    if unit_vectors:
        logger.debug("mags.max() = {0}".format(mags.max()))
        logger.debug("mags = {0}".format(mags[100:150]))

        ax.quiver(x, y, dx/mags, dy/mags, mags, cmap=colormap)
    else:
        # ax.quiver(x, y, dx, dy, mags, cmap=colormap)
        ax.quiver(x, y, dx/mags, dy/mags, mags, cmap=colormap,norm=norm)

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
    

def contourf_response(lon,
                      lat,
                      data,
                      request,
                      dpi=80,
                      nlvls = 15):

    logger.info("Rendering c-grid countourf.")

    xmin, ymin, xmax, ymax = wms_handler.get_bbox(request)
    logger.debug("xmin, ymin, xmax, ymax = {0}".format([xmin, ymin, xmax, ymax]))

    width, height = wms_handler.get_width_height(request)
    logger.debug("width = {0}, height = {1}".format(width, height))

    colormap = wms_handler.get_colormap(request)
    logger.debug("colormap = {0}".format(colormap))

    cmin, cmax = wms_handler.get_climits(request)
    logger.debug("cmin = {0}, cmax = {1}".format(cmin, cmax))

    proj = get_pyproj(request)

    logger.debug("Projecting topology")
    xcrs, ycrs = proj(lon.flatten(),lat.flatten())
    logger.debug("Done projecting topology")

    xcrs = xcrs.reshape(data.shape)
    ycrs = ycrs.reshape(data.shape)

    logger.debug("xcrs.shape = {0}".format(xcrs.shape))
    logger.debug("ycrs.shape = {0}".format(ycrs.shape))
    logger.debug("data.shape = {0}".format(data.shape))

    fig = Figure(dpi=dpi, facecolor='none', edgecolor='none')
    fig.set_alpha(0)
    fig.set_figheight(height/dpi)
    fig.set_figwidth(width/dpi)

    ax = fig.add_axes([0., 0., 1., 1.], xticks=[], yticks=[])
    lvls = np.linspace(cmin, cmax, nlvls)

    ax.contourf(xcrs, ycrs, data, levels=lvls, cmap=colormap)

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_frame_on(False)
    ax.set_clip_on(False)
    ax.set_position([0, 0, 1, 1])
    
    canvas = FigureCanvasAgg(fig)
    
    response = HttpResponse(content_type='image/png')
    canvas.print_png(response)

    logger.debug("Finished Rendering c-grid contourf")
    
    return response
        


