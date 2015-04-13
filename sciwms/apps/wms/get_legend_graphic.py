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

Created on Sep 1, 2011

@author: ACrosby
'''

import os
import gc
import sys
import json
import bisect
import logging
import datetime
import traceback
import subprocess
import multiprocessing
import time as timeobj
from urlparse import urlparse
try:
    import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

import numpy
import netCDF4

# Import from matplotlib and set backend
import matplotlib
#matplotlib.use("Agg")
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg

import pyproj

# Other random "from" imports
from rtree import index as rindex
from collections import deque
from StringIO import StringIO  # will be deprecated in Python3, use io.byteIO instead

from django.conf import settings
from django.contrib.sites.models import Site
from django.template.loader import get_template
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ObjectDoesNotExist
import django.shortcuts

from sciwms.apps.wms.models import Dataset, Server, Group, VirtualLayer
from sciwms.util import cf

import pyugrid
import numpy as np

from .get_map import getMap
from .get_feature_info import getFeatureInfo

from ...util import cf

#output_path = os.path.join(settings.PROJECT_ROOT, 'logs', 'sciwms_wms.log')
## Set up Logger
logger = multiprocessing.get_logger()
#logger.setLevel(logging.DEBUG)
#handler = logging.FileHandler(output_path)
#formatter = logging.Formatter(fmt='[%(asctime)s] - <<%(levelname)s>> - |%(message)s|')
#handler.setFormatter(formatter)
#logger.addHandler(handler)

# added for getLegendGraphic, to place the verical level in the legend
def _get_vertical_level(nc, v):
    # get the coordinates attribute
    coordinates = getattr(v, 'coordinates', None)
    for coordinate in coordinates.split():
        if nc.variables[coordinate].shape == (v.shape[1],): # TODO second index is vert?
            z = nc.variables[coordinate]
            units = getattr(z, 'units', None)
            logger.debug('units {0}'.format(units))
            if units is not None and units.strip():
                return '%s\n%s' % (str(z[0]), units)
            long_name = getattr(z, 'long_name', None)
            logger.debug('long_name {0}'.format(long_name))
            if long_name is not None and long_name.strip():
                return '%s\n%s' % (str(z[0]), long_name)
            return str(z[0])

def getLegendGraphic(request, dataset):
    """
    Parse parameters from request that looks like this:

    http://webserver.smast.umassd.edu:8000/wms/NecofsWave?
    ELEVATION=1
    &LAYERS=hs
    &TRANSPARENT=TRUE
    &STYLES=facets_average_jet_0_0.5_node_False
    &SERVICE=WMS
    &VERSION=1.1.1
    &REQUEST=GetLegendGraphic
    &FORMAT=image%2Fpng
    &TIME=2012-06-20T18%3A00%3A00
    &SRS=EPSG%3A3857
    &LAYER=hs
    """
    styles = request.GET["styles"].split("_")
    try:
        climits = (float(styles[3]), float(styles[4]))
    except:
        climits = (None, None)
    variables = request.GET["layer"].split(",")
    plot_type = styles[0]
    colormap = styles[2].replace('-', '_')

    # direct the service to the dataset
    # make changes to server_local_config.py
    if settings.LOCALDATASET:
        url = settings.LOCALDATASETPATH[dataset]
    else:
        url = Dataset.objects.get(name=dataset).path()
    nc = netCDF4.Dataset(url)

    """
    Create figure and axes for small legend image
    """
    #from matplotlib.figure import Figure
    from matplotlib.pylab import get_cmap
    fig = Figure(dpi=100., facecolor='none', edgecolor='none')
    fig.set_alpha(0)
    fig.set_figwidth(1*1.3)
    fig.set_figheight(1.5*1.3)

    """
    Create the colorbar or legend and add to axis
    """
    v = cf.get_by_standard_name(nc, variables[0])

    try:
        units = v.units
    except:
        units = ''
    # vertical level label
    if v.ndim > 3:
        units = units + '\nvertical level: %s' % _get_vertical_level(nc, v)
    if climits[0] is None or climits[1] is None:  # TODO: NOT SUPPORTED RESPONSE
            #going to have to get the data here to figure out bounds
            #need elevation, bbox, time, magnitudebool
            CNorm = None
            ax = fig.add_axes([0, 0, 1, 1])
            ax.grid(False)
            ax.text(.5, .5, 'Error: No Legend\navailable for\nautoscaled\ncolor styles!', ha='center', va='center', transform=ax.transAxes, fontsize=8)
    elif plot_type not in ["contours", "filledcontours"]:
        #use limits described by the style
        ax = fig.add_axes([.01, .05, .2, .8])  # xticks=[], yticks=[])
        CNorm = matplotlib.colors.Normalize(vmin=climits[0],
                                            vmax=climits[1],
                                            clip=False,
                                            )
        cb = matplotlib.colorbar.ColorbarBase(ax,
                                              cmap=get_cmap(colormap),
                                              norm=CNorm,
                                              orientation='vertical',
                                              )
        cb.set_label(units, size=8)

    else:  # plot type somekind of contour
        if plot_type == "contours":
            #this should perhaps be a legend...
            #ax = fig.add_axes([0,0,1,1])
            fig_proxy = Figure(frameon=False, facecolor='none', edgecolor='none')
            ax_proxy = fig_proxy.add_axes([0, 0, 1, 1])
            CNorm = matplotlib.colors.Normalize(vmin=climits[0], vmax=climits[1], clip=True)
            #levs = numpy.arange(0, 12)*(climits[1]-climits[0])/10
            levs = numpy.linspace(climits[0], climits[1], 11)
            x, y = numpy.meshgrid(numpy.arange(10), numpy.arange(10))
            cs = ax_proxy.contourf(x, y, x, levels=levs, norm=CNorm, cmap=get_cmap(colormap))

            proxy = [plt.Rectangle((0, 0), 0, 0, fc=pc.get_facecolor()[0]) for pc in cs.collections]

            fig.legend(proxy, levs,
                       #bbox_to_anchor = (0, 0, 1, 1),
                       #bbox_transform = fig.transFigure,
                       loc = 6,
                       title = units,
                       prop = { 'size' : 8 },
                       frameon = False,
                       )
        elif plot_type == "filledcontours":
            #this should perhaps be a legend...
            #ax = fig.add_axes([0,0,1,1])
            fig_proxy = Figure(frameon=False, facecolor='none', edgecolor='none')
            ax_proxy = fig_proxy.add_axes([0, 0, 1, 1])
            CNorm = matplotlib.colors.Normalize(vmin=climits[0], vmax=climits[1], clip=False,)
            #levs = numpy.arange(1, 12)*(climits[1]-(climits[0]))/10
            levs = numpy.linspace(climits[0], climits[1], 10)
            levs = numpy.hstack(([-99999], levs, [99999]))

            x, y = numpy.meshgrid(numpy.arange(10), numpy.arange(10))
            cs = ax_proxy.contourf(x, y, x, levels=levs, norm=CNorm, cmap=get_cmap(colormap))

            proxy = [plt.Rectangle((0, 0), 0, 0, fc=pc.get_facecolor()[0]) for pc in cs.collections]

            levels = []
            for i, value in enumerate(levs):
                #if i == 0:
                #    levels[i] = "<" + str(value)
                if i == len(levs)-2 or i == len(levs)-1:
                    levels.append("> " + str(value))
                elif i == 0:
                    levels.append("< " + str(levs[i+1]))
                else:
                    #levels.append(str(value) + "-" + str(levs[i+1]))
                    text = '%.2f-%.2f' % (value, levs[i+1])
                    levels.append(text)
            fig.legend(proxy, levels,
                       #bbox_to_anchor = (0, 0, 1, 1),
                       #bbox_transform = fig.transFigure,
                       loc = 6,
                       title = units,
                       prop = { 'size' : 6 },
                       frameon = False,
                       )

    canvas = FigureCanvasAgg(fig)
    response = HttpResponse(content_type='image/png')
    canvas.print_png(response)
    nc.close()
    return response


