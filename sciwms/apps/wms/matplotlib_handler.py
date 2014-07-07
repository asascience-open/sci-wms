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

import pyproj

from . import wms_handler
from ...util.cf import get_by_standard_name
from ...util import get_pyproj

import numpy as np

import netCDF4

logger = multiprocessing.get_logger()
EPSG4326 = pyproj.Proj(init='EPSG:4326')


def get_lat_lon_subset_idx(lon,lat,lonmin,latmin,lonmax,latmax,padding=0.18):
    """
    A function to return the indicies of lat, lon within a bounding box.
    Padding is leftover from old sciwms code, I believe it was to include triangles
    lying just outside the region of interest so that there are no holes in the
    rendered image.
    """
    if lonmin > lonmax:
        lonmin = lonmin * -1.0 # TODO: this should solve USW integration sites at wide zoom, but is it best way?
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
        logger.warning("ERROR: get_nearest_start_time:: "
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

    xmin, ymin, xmax, ymax = wms_handler.get_bbox(request)

    #proj = get_pyproj(request)
    #lonmin, latmin = proj(xmin, ymin, inverse=True)
    #lonmax, latmax = porj(xmax, ymax, inverse=True)
    CRS = get_pyproj(request)
    lonmin, latmin = pyproj.transform(CRS, EPSG4326, xmin, ymin)
    lonmax, latmax = pyproj.transform(CRS, EPSG4326, xmax, ymax)
    #logger.info("lonmin, latmin: {0} {1}".format(lonmin, latmin))
    #logger.info("lonmax, latmax: {0} {1}".format(lonmax, latmax))


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

    xmin, ymin, xmax, ymax = wms_handler.get_bbox(request)
    width, height = wms_handler.get_width_height(request)
    
    colormap = wms_handler.get_colormap(request)
    
    cmin, cmax = wms_handler.get_climits(request)
    #logger.info('cmin/cmax: {0} {1}'.format(cmin, cmax))

    # TODO: check this?
    try:
        data[data>cmax] = cmax
        data[data<cmin] = cmin
    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.warning("tricontourf_response error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    
    clvls = wms_handler.get_clvls(request)

    #proj = get_pyproj(request)
    #triang_subset.x, triang_subset.y = proj(triang_subset.x, triang_subset.y)
    CRS = get_pyproj(request)
    triang_subset.x, triang_subset.y = pyproj.transform(EPSG4326, CRS, triang_subset.x, triang_subset.y) #TODO order for non-inverse?
    #logger.info('TRANSFORMED triang_subset.x: {0}'.format(triang_subset.x))
    #logger.info('TRANSFORMED triang_subset.y: {0}'.format(triang_subset.y))

    fig = Figure(dpi=dpi, facecolor='none', edgecolor='none')
    fig.set_alpha(0)
    fig.set_figheight(height/dpi)
    fig.set_figwidth(width/dpi)

    ax = fig.add_axes([0., 0., 1., 1.], xticks=[], yticks=[])
    ax.set_axis_off()

    lvls = np.linspace(float(cmin), float(cmax), int(clvls))
    #logger.info('trang.shape: {0}'.format(triang_subset.x.shape))
    #logger.info('data.shape: {0}'.format(data.shape))
    ax.tricontourf(triang_subset, data, levels = lvls, cmap=colormap)

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)

    ax.set_frame_on(False)
    ax.set_clip_on(False)
    ax.set_position([0., 0., 1., 1.])

    #plt.axis('off')

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
    
    from django.http import HttpResponse

    xmin, ymin, xmax, ymax = wms_handler.get_bbox(request)
    width, height = wms_handler.get_width_height(request)
    
    colormap = wms_handler.get_colormap(request)

    climits = wms_handler.get_climits(request)

    cmax = 1.
    cmin = 0.
    
    if len(climits) == 2:
        cmin, cmax = climits
    else:
        logger.debug("No climits, default cmax to 1.0")

    # cmax = 10.

    #proj = get_pyproj(request)
    #x, y = proj(lon, lat)
    CRS = get_pyproj(request)
    x, y = pyproj.transform(EPSG4326, CRS, lon, lat) #TODO order for non-inverse?
    #logger.info("x, y: {0} {1}".format(x, y))
    
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
    mags[mags>cmax] = cmax
    mags[mags<cmin] = cmin

    import matplotlib as mpl
    cmap = mpl.cm.get_cmap(colormap)
    bounds = np.linspace(cmin, cmax, 15)
    norm = mpl.colors.BoundaryNorm(bounds, cmap.N)

    #plot unit vectors
    if unit_vectors:
        ax.quiver(x, y, dx/mags, dy/mags, mags, cmap=colormap)
    else:
        ax.quiver(x, y, dx, dy, mags, cmap=cmap, norm=norm)
        #ax.quiver(x, y, dx/mags, dy/mags, mags, cmap=colormap,norm=norm)

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_frame_on(False)
    ax.set_clip_on(False)
    ax.set_position([0., 0., 1., 1.])

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

    xmin, ymin, xmax, ymax = wms_handler.get_bbox(request)

    width, height = wms_handler.get_width_height(request)

    colormap = wms_handler.get_colormap(request)

    cmin, cmax = wms_handler.get_climits(request)

    #proj = get_pyproj(request)
    #xcrs, ycrs = proj(lon.flatten(),lat.flatten())
    CRS = get_pyproj(request)
    xcrs, ycrs = pyproj.transform(EPSG4326, CRS, lon.flatten(),lat.flatten()) #TODO order for non-inverse?
    #logger.info("xcrs, ycrs: {0} {1}".format(xcrs, ycrs))

    xcrs = xcrs.reshape(data.shape)
    ycrs = ycrs.reshape(data.shape)

    sxcrs = np.argsort(xcrs[1,:])
    sycrs = np.argsort(ycrs[:,1])

    fig = Figure(dpi=dpi, facecolor='none', edgecolor='none')
    fig.set_alpha(0)
    fig.set_figheight(height/dpi)
    fig.set_figwidth(width/dpi)

    ax = fig.add_axes([0., 0., 1., 1.], xticks=[], yticks=[])
    lvls = np.linspace(cmin, cmax, nlvls)

    #ax.contourf(xcrs, ycrs, data, levels=lvls, cmap=colormap)
    ax.contourf(xcrs[sycrs,:][:,sxcrs], ycrs[sycrs,:][:,sxcrs], data[sycrs,:][:,sxcrs], levels=lvls, cmap=colormap)

    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    ax.set_frame_on(False)
    ax.set_clip_on(False)
    ax.set_position([0, 0, 1, 1])
    
    canvas = FigureCanvasAgg(fig)
    
    response = HttpResponse(content_type='image/png')
    canvas.print_png(response)

    return response
        
def colormaps(request):
    """
    Get either a json list of available matplotlib colormaps or return an image preview.
    EX 1 localhost:8080/wms/colormaps will return a list of colormaps
    EX 2 localhost:8080/wms/colormaps/colormap=summer will return a small png preview
    """
    #if not requesting a specific colormap, get a list (json) of colormaps
    #if requesting a specific colormap, get a small png preview
    colormap = request.GET.get('colormap',"").replace('-','_')
    if not colormap:
        import matplotlib.pyplot as plt
        ret = json.dumps([m.replace('_','-') for m in plt.cm.datad if not m.endswith("_r")])
        if 'callback' in request.REQUEST:
            ret = "{0}({1})".format(request.REQUEST['callback'], ret)

        return HttpResponse(ret, mimetype='application/json')
    else:
        import numpy as np
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_agg import FigureCanvasAgg

        a = np.linspace(0,1,256).reshape(1,-1)
        a = np.vstack((a,a))


        fig = plt.figure(dpi=100., facecolor='none', edgecolor='none')
        fig.set_alpha(0)

        #get request should be in units of pixels
        w_pixels = float(request.GET.get('w',400.))
        h_pixels = float(request.GET.get('h',10.4))
        dpi = float(request.GET.get('dpi',80.))
        w_inches = w_pixels/dpi
        h_inches = h_pixels/dpi

        fig.set_figwidth(w_inches)
        fig.set_figheight(h_inches)

        ax = fig.add_axes([0.,0.,1.,1.], xticks=[], yticks=[])
        ax.set_axis_off();
        ax.imshow(a, aspect='auto',cmap=plt.get_cmap(colormap))

        canvas = FigureCanvasAgg(fig)
        response = HttpResponse(content_type='image/png')
        canvas.print_png(response)
        return response


