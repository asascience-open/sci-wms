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

Created on Oct 17, 2011

@author: ACrosby
'''
import multiprocessing

import numpy as np

from datetime import date
from django.conf import settings

logger = multiprocessing.get_logger()

def get_bbox(request):
    """
    Return the [lonmin, latmin, lonmax, lonmax] - [lower (x,y), upper(x,y)]
    Units will be specified by projection.
    """
    return [float(el) for el in request.GET["bbox"].split(",")]

def get_projection_string(request):
    """
    Return the projection string passed into the request.
    Can be specified by \"SRS\" or \"CRS\" key (string).
    If \"SRS\" or \"CRS\" is not available, default to mercator.
    """
    projstr = request.GET.get("SRS")    
    if not projstr:
        projstr = request.GET.get("CRS")

    if not projstr:
        projstr = "EPSG:3857"
        logger.info("SRS or CRS no available in requst, defaulting to EPSG:3857 (mercator)")

    return projstr

def get_xy(request):
    """
    Returns list of floats
    """
    xy = [None, None]
    x = request.GET.get('x')
    if x:
        xy[0] = float(x)
    y = request.GET.get('y')
    if y:
        xy[1] = float(y)

    return xy

def get_layers(request):
    """
    Returns a list of strings
    """
    return request.GET.get("LAYERS").split(",")

def get_elevation(request):
    """
    Return the elevation
    """
    try:
        elev = request.GET["elevation"]
        if elev == "":
            return "0"
    except:
        return "0"

    return elev

def get_date_start_end(request):
    time = request.GET.get('time')
    if not time:
        time = date.today().isoformat() + "T00:00:00"
    logger.debug("get_date_start_end::time = {0}".format(time))
    # try:
    #     time = request.GET.get('time')
    #     logger.debug("get_date_start_end::time = {0}".format(time))
    #     if not time:
    #         now = date.today().isoformat()
    #         time = now + "T00:00:00"#
    # except:
    #     now = date.today().isoformat()
    #     time = now + "T00:00:00"#
    time = time.split("/")

    for i in range(len(time)):
        time[i] = time[i].replace("Z", "")
        if len(time[i]) == 16:
            time[i] = time[i] + ":00"
        elif len(time[i]) == 13:
            time[i] = time[i] + ":00:00"
        elif len(time[i]) == 10:
            time[i] = time[i] + "T00:00:00"
    if len(time) > 1:
        timestart = time[0]
        timeend = time[1]
    else:
        timestart = time[0]
        timeend = time[0]

    return timestart, timeend

def get_style_list(request):
    try:
        return request.GET["styles"].split(",")[0].split("_")
    except:
        return []
    
def get_colormap(request):
    """
    Return style string from a list of styles
    (as returned by get_style_list function)
    """
    try:
        styles = get_style_list(request)
        if styles:
            return styles[2].replace("-","_")
        return "jet"
    except:
        logger.debug("Using default colormap (jet)")
        return "jet"

def get_climits(request):
    styles = get_style_list(request)
    if styles:
        return np.array(styles[3:5],dtype=np.float)
    else:
        return []

def get_clvls(request):
    try:
        styles = get_style_list(request)
        return int(styles[5])
    except:
        logger.debug("Using default clvls (15)")
        return 15
    
# def get_topology_type(request):
#     styles = get_style_list(request)
#     if styles:
#         return styles[5]
#     else:
#         return None

def get_elevation(request):
    """
    Return WMS 'ELEVATION' (AKA z coordinate)
    """
    try:
        return float(request.GET["ELEVATION"])
    except:
        return 0

def get_width_height(request):
    """
    Return width and height of requested view.
    RETURNS width, height request should be in pixel units.
    """
    try:
        width = float(request.GET.get("width"))
        height = float(request.GET.get("height"))
        return width, height
    except:
        return []

def get_magnitude_bool(styles):
    styles = get_style_list(request)
    if styles:
        return styles[6]
    else:
        return None   
