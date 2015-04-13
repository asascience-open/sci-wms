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

def getCapabilities(req, dataset):  # TODO move get capabilities to template system like sciwps
    # Create the object to be encoded to xml later
    root = ET.Element('WMT_MS_Capabilities')
    root.attrib["version"] = "1.1.1"
    href = "http://" + req.META['HTTP_HOST'] + req.META['PATH_INFO'] + "?"
    virtual_layers = VirtualLayer.objects.filter(datasets__name=dataset)
    expected_configurations = {"u"       : ("u,v", ","),
                               "u-vel"   : ("u-vel,v-vel", ","),
                               "ua"      : ("ua,va", ","),
                               "U"       : ("U,V", ","),
                               "uc"      : ("uc,vc", ","),
                               "air_u"   : ("air_u,air_v", ","),
                               "water_u" : ("water_u,water_v", ",")
                              }
    virtual_configurations = {}
    for layer in list(virtual_layers):
        if "*" in layer.layer_expression:
            virtual_configurations[layer.layer_expression.split("*")[0]] = (layer.layer, "*")
        elif "+" in layer.layer_expression:
            virtual_configurations[layer.layer_expression.split("+")[0]] = (layer.layer, "+")
        elif "," in layer.layer_expression:
            virtual_configurations[layer.layer_expression.split(",")[0]] = (layer.layer, ",")

    # Plug into your generic implentation of sciwms template
    # will have to pull these fields out of the database directly
    # to ensure uptodate
    service = ET.SubElement(root, 'Service')

    servermetadata = Server.objects.values()[0]
    ET.SubElement(service, "Name").text = "OGC:WMS"
    ET.SubElement(service, "Title").text = servermetadata["title"]
    ET.SubElement(service, "Abstract").text = servermetadata["abstract"]
    keywordlist = ET.SubElement(service, "KeywordList")
    keywords       = servermetadata["keywords"].split(",")
    for keyword in keywords:
        ET.SubElement(keywordlist, "Keyword").text = keyword
    onlineresource = ET.SubElement(service, "OnlineResource")
    onlineresource.attrib["xlink:type"] = "simple"
    onlineresource.attrib["xmlns:xlink"] = "http://www.w3.org/1999/xlink"
    #Contact Information
    contactinformation = ET.SubElement(service, "ContactInformation")
    primarycontact = ET.SubElement(contactinformation, "ContactPersonPrimary")
    ET.SubElement(primarycontact, "ContactPerson").text = servermetadata["contact_person"]
    ET.SubElement(primarycontact, "ContactOrganization").text = servermetadata["contact_organization"]
    ET.SubElement(contactinformation, "ContactPosition").text = servermetadata["contact_position"]
    contactaddress = ET.SubElement(contactinformation, "ContactAddress")
    ET.SubElement(contactaddress, "AddressType").text = "postal"
    ET.SubElement(contactaddress, "Address").text = servermetadata["contact_street_address"]
    ET.SubElement(contactaddress, "City").text = servermetadata["contact_city_address"]
    ET.SubElement(contactaddress, "StateOrProvince").text = servermetadata["contact_state_address"]
    ET.SubElement(contactaddress, "PostCode").text = servermetadata['contact_code_address']
    ET.SubElement(contactaddress, "Country").text = servermetadata['contact_country_address']
    ET.SubElement(contactinformation, "ContactVoiceTelephone").text = servermetadata['contact_telephone']
    ET.SubElement(contactinformation, "ContactElectronicMailAddress").text = servermetadata['contact_email']

    # Capability elements (hardcoded)
    capability = ET.SubElement(root, "Capability")
    request = ET.SubElement(capability, "Request")
    # GetCaps
    getcaps = ET.SubElement(request, "GetCapabilities")
    ET.SubElement(getcaps, "Format").text = "application/vnd.ogc.wms_xml"
    ET.SubElement(getcaps, "Format").text = "text/xml"
    getcaps_dcptype = ET.SubElement(getcaps, "DCPType")
    getcaps_http = ET.SubElement(getcaps_dcptype, "HTTP")
    getcaps_get = ET.SubElement(getcaps_http, "Get")
    getcaps_onlineresource = ET.SubElement(getcaps_get, "OnlineResource")
    getcaps_onlineresource.attrib["xlink:type"] = "simple"
    getcaps_onlineresource.attrib["xlink:href"] = href
    getcaps_onlineresource.attrib["xmlns:xlink"] = "http://www.w3.org/1999/xlink"
    # GetMap
    getmap = ET.SubElement(request, "GetMap")
    ET.SubElement(getmap, "Format").text = "image/png"
    #ET.SubElement(getmap, "Format").text = "text/csv"
    #ET.SubElement(getmap, "Format").text = "application/netcdf"
    #ET.SubElement(getmap, "Format").text = "application/matlab-mat"
    #ET.SubElement(getmap, "Format").text = "application/x-zip-esrishp"
    getmap_dcptype = ET.SubElement(getmap, "DCPType")
    getmap_http = ET.SubElement(getmap_dcptype, "HTTP")
    getmap_get = ET.SubElement(getmap_http, "Get")
    getmap_onlineresource = ET.SubElement(getmap_get, "OnlineResource")
    getmap_onlineresource.attrib["xlink:type"] = "simple"
    getmap_onlineresource.attrib["xlink:href"] = href
    getmap_onlineresource.attrib["xmlns:xlink"] = "http://www.w3.org/1999/xlink"
    # GetFeatureInfo
    gfi = ET.SubElement(request, "GetFeatureInfo")
    ET.SubElement(gfi, "Format").text = "image/png"
    ET.SubElement(gfi, "Format").text = "text/csv"
    ET.SubElement(gfi, "Format").text = "text/javascript"
    #ET.SubElement(gfi, "Format").text = "text/csv"
    #ET.SubElement(gfi, "Format").text = "application/netcdf"
    #ET.SubElement(gfi, "Format").text = "application/matlab-mat"
    #ET.SubElement(gfi, "Format").text = "application/x-zip-esrishp"
    gfi_dcptype = ET.SubElement(gfi, "DCPType")
    gfi_http = ET.SubElement(gfi_dcptype, "HTTP")
    gfi_get = ET.SubElement(gfi_http, "Get")
    gfi_onlineresource = ET.SubElement(gfi_get, "OnlineResource")
    gfi_onlineresource.attrib["xlink:type"] = "simple"
    gfi_onlineresource.attrib["xlink:href"] = href
    gfi_onlineresource.attrib["xmlns:xlink"] = "http://www.w3.org/1999/xlink"
    # GetLegendGraphic
    getlegend = ET.SubElement(request, "GetLegendGraphic")
    ET.SubElement(getlegend, "Format").text = "image/png"
    getlegend_dcptype = ET.SubElement(getlegend, "DCPType")
    getlegend_http = ET.SubElement(getlegend_dcptype, "HTTP")
    getlegend_get = ET.SubElement(getlegend_http, "Get")
    getlegend_onlineresource = ET.SubElement(getlegend_get, "OnlineResource")
    getlegend_onlineresource.attrib["xlink:type"] = "simple"
    getlegend_onlineresource.attrib["xlink:href"] = href
    getlegend_onlineresource.attrib["xmlns:xlink"] = "http://www.w3.org/1999/xlink"
    #Exception
    exception = ET.SubElement(capability, "Exception")
    ET.SubElement(exception, "Format").text = "text/html"

    # Pull layer description directly from database
    onlineresource.attrib["href"] = href
    # Layers
    layer = ET.SubElement(capability, "Layer")
    ET.SubElement(layer, "Title").text      = Dataset.objects.get(name=dataset).name
    ET.SubElement(layer, "Abstract").text   = Dataset.objects.get(name=dataset).description
    ET.SubElement(layer, "SRS").text        = "EPSG:3857"
    #ET.SubElement(layer, "SRS").text        = "MERCATOR"
    nc = netCDF4.Dataset(Dataset.objects.get(name=dataset).path())
    topology = netCDF4.Dataset(os.path.join(settings.TOPOLOGY_PATH, dataset + '.nc'))
    #list_timesteps = Dataset.objects.get(name=dataset).display_all_timesteps

    # handle time here, so we're not doing it within the loop of variables
    list_timesteps = False # only print range, so slow otherwise
    time_extent_text='unknown'
    try:
        remote_time = cf.get_by_standard_name(nc, 'time')
        try:
            units = remote_time.units
            if len(remote_time) == 1:
                time_extent_text = netCDF4.num2date(remote_time[0], units).isoformat('T')+"Z"
            else:
                if list_timesteps:
                    temptime = [netCDF4.num2date(i, units).isoformat('T')+"Z" for i in remote_time[:]]
                    time_extent_text = temptime.__str__().strip("[]").replace("'", "").replace(" ", "")
                else:
                    time_extent_text = netCDF4.num2date(remote_time[0], units).isoformat('T')+"Z/" + netCDF4.num2date(remote_time[-1], units).isoformat('T')+"Z"
        except:
            if len(remote_time) == 1:
                time_extent_text = str(remote_time[0])
            else:
                time_extent_text = str(remote_time[0]) + "/" + str(remote_time[-1])
    except:
        pass

    # TODO: use LAYERS
    for variable in nc.variables.keys():

        if nc.variables[variable].ndim > 1: # TODO: only publish variables with more than a single dimension? only CF standard_name?

            layer1 = ET.SubElement(layer, "Layer")
            layer1.attrib["queryable"] = "1"
            layer1.attrib["opaque"] = "0"
            ET.SubElement(layer1, "Name").text = variable
            try:
                try:
                    ET.SubElement(layer1, "Title").text = nc.variables[variable].standard_name
                except:
                    ET.SubElement(layer1, "Title").text = nc.variables[variable].long_name
            except:
                ET.SubElement(layer1, "Title").text = variable
            try:
                try:
                    ET.SubElement(layer1, "Abstract").text = nc.variables[variable].summary
                except:
                    ET.SubElement(layer1, "Abstract").text = nc.variables[variable].long_name
            except:
                ET.SubElement(layer1, "Abstract").text = variable
            ET.SubElement(layer1, "SRS").text = "EPSG:3857"
            llbbox = ET.SubElement(layer1, "LatLonBoundingBox")
            try:
                templon = cf.get_by_standard_name(topology, 'longitude')[:]
                templat = cf.get_by_standard_name(topology, 'latitude')[:]
            except:
                ug = pyugrid.UGrid.from_ncfile(os.path.join(settings.TOPOLOGY_PATH, dataset + '.nc'))
                templon = ug.nodes[:,0]
                templat = ug.nodes[:,1]
            llbbox.attrib["minx"] = str(numpy.nanmin(templon))
            llbbox.attrib["miny"] = str(numpy.nanmin(templat))
            llbbox.attrib["maxx"] = str(numpy.nanmax(templon))
            llbbox.attrib["maxy"] = str(numpy.nanmax(templat))
            llbbox = ET.SubElement(layer1, "BoundingBox")
            llbbox.attrib["SRS"] = "EPSG:4326"
            llbbox.attrib["minx"] = str(numpy.nanmin(templon))
            llbbox.attrib["miny"] = str(numpy.nanmin(templat))
            llbbox.attrib["maxx"] = str(numpy.nanmax(templon))
            llbbox.attrib["maxy"] = str(numpy.nanmax(templat))
            time_dimension = ET.SubElement(layer1, "Dimension")
            time_dimension.attrib["name"] = "time"
            time_dimension.attrib["units"] = "ISO8601"
            elev_dimension = ET.SubElement(layer1, "Dimension")
            elev_dimension.attrib["name"] = "elevation"
            elev_dimension.attrib["units"] = "EPSG:5030"
            time_extent = ET.SubElement(layer1, "Extent")
            time_extent.attrib["name"] = "time"
            time_extent.text = time_extent_text
            elev_extent = ET.SubElement(layer1, "Extent")
            elev_extent.attrib["name"] = "elevation"
            elev_extent.attrib["default"] = "0"

#            # TODO: this needs to be worked on DEPTH SECTION (DON'T JUST REMOVE)
#            ## Listing all available elevation layers is a tough thing to do for the range of types of datasets...
#            if topology.grid.lower() == 'false':
#                if nc.variables[variable].ndim > 2:
#                    try:
#                        ET.SubElement(layer1, "DepthLayers").text = str(range(nc.variables["siglay"].shape[0])).replace("[", "").replace("]", "").replace(" ", "")
#                        elev_extent.text = str(range(nc.variables["siglay"].shape[0])).replace("[", "").replace("]", "").replace(" ", "")
#                    except:
#                        ET.SubElement(layer1, "DepthLayers").text = ""
#                    try:
#                        if nc.variables["siglay"].positive.lower() == "up":
#                            ET.SubElement(layer1, "DepthDirection").text = "Down"
#                        elif nc.variables["siglay"].positive.lower() == "down":
#                            ET.SubElement(layer1, "DepthDirection").text = "Up"
#                        else:
#                            ET.SubElement(layer1, "DepthDirection").text = ""
#                    except:
#                        ET.SubElement(layer1, "DepthDirection").text = ""
#                else:
#                    ET.SubElement(layer1, "DepthLayers").text = "0"
#                    ET.SubElement(layer1, "DepthDirection").text = "Down"
##                    elev_extent.text = "0"
#            elif topology.grid.lower() == 'cgrid':
#                if nc.variables[variable].ndim > 3:
#                    try:
#                        ET.SubElement(layer1, "DepthLayers").text = str(range(nc.variables[variable].shape[1])).replace("[", "").replace("]", "").replace(" ", "")
##                        elev_extent.text = str(range(nc.variables[variable].shape[1])).replace("[", "").replace("]", "").replace(" ", "")
#                    except:
#                        ET.SubElement(layer1, "DepthLayers").text = ""
#                    try:
#                        #if nc.variables["depth"].positive.lower() == "up":
#                        #    ET.SubElement(layer1, "DepthDirection").text = "Down"
#                        #elif nc.variables["depth"].positive.lower() == "down":
#                        #    ET.SubElement(layer1, "DepthDirection").text = "Up"
#                        #else:
#                        #    ET.SubElement(layer1, "DepthDirection").text = ""
#                        ET.SubElement(layer1, "DepthDirection").text = ""
#                    except:
#                        ET.SubElement(layer1, "DepthDirection").text = ""
#                else:
#                    ET.SubElement(layer1, "DepthLayers").text = "0"
#                    ET.SubElement(layer1, "DepthDirection").text = "Down"
#                    elev_extent.text = "0"
#            else:
#                ET.SubElement(layer1, "DepthLayers").text = "0"
#                ET.SubElement(layer1, "DepthDirection").text = "Down"
#                elev_extent.text = "0"
#            ##

            for style in ["filledcontours", "contours", "pcolor", "facets"]:
                #style_code = style + "_average_jet_None_None_" + location + "_False" # TODO: getting rid of the grid location crap
                style_code = style + "_average_jet_None_None_None_False"
                style = ET.SubElement(layer1, "Style")
                ET.SubElement(style, "Name").text = style_code
                ET.SubElement(style, "Title").text = style_code
                ET.SubElement(style, "Abstract").text = "http://" + Site.objects.values()[0]['domain'] + "/doc"
                legendurl = ET.SubElement(style, "LegendURL")
                legendurl.attrib["width"] = "50"
                legendurl.attrib["height"] = "80"
                ET.SubElement(legendurl, "Format").text = "image/png"
                #legend_onlineresource = ET.SubElement(legendurl, "OnlineResource")
                #legend_onlineresource.attrib["xlink:type"] = "simple"
                #legend_onlineresource.attrib["xlink:href"] = href
                #legend_onlineresource.attrib["xmlns:xlink"] = "http://www.w3.org/1999/xlink"
            for configurations in [expected_configurations, virtual_configurations]:
                if variable in configurations:
                    layername, layertype = configurations[variable]
                    layer1 = ET.SubElement(layer, "Layer")
                    layer1.attrib["queryable"] = "1"
                    layer1.attrib["opaque"] = "0"
                    ET.SubElement(layer1, "Name").text = layername
                    ET.SubElement(layer1, "Title").text = layername  # current velocity (u,v)"
                    if layertype == "*":
                        typetext = "3 band true color composite"
                    elif layertype == "+":
                        typetext = "sum or addition of two layers"
                    elif layertype == ",":
                        typetext = "magnitude or vector layer"
                    ET.SubElement(layer1, "Abstract").text = "Virtual Layer, "+typetext  # "Magnitude of current velocity from u and v components"
                    ET.SubElement(layer1, "SRS").text = "EPSG:4326"
                    llbbox = ET.SubElement(layer1, "LatLonBoundingBox")
                    llbbox.attrib["minx"] = str(numpy.nanmin(templon))
                    llbbox.attrib["miny"] = str(numpy.nanmin(templat))
                    llbbox.attrib["maxx"] = str(numpy.nanmax(templon))
                    llbbox.attrib["maxy"] = str(numpy.nanmax(templat))
                    llbbox = ET.SubElement(layer1, "BoundingBox")
                    llbbox.attrib["SRS"] = "EPSG:4326"
                    llbbox.attrib["minx"] = str(numpy.nanmin(templon))
                    llbbox.attrib["miny"] = str(numpy.nanmin(templat))
                    llbbox.attrib["maxx"] = str(numpy.nanmax(templon))
                    llbbox.attrib["maxy"] = str(numpy.nanmax(templat))
                    time_dimension = ET.SubElement(layer1, "Dimension")
                    time_dimension.attrib["name"] = "time"
                    time_dimension.attrib["units"] = "ISO8601"
                    elev_dimension = ET.SubElement(layer1, "Dimension")
                    elev_dimension.attrib["name"] = "elevation"
                    elev_dimension.attrib["units"] = "EPSG:5030"
                    time_extent = ET.SubElement(layer1, "Extent")
                    time_extent.attrib["name"] = "time"
                    elev_extent = ET.SubElement(layer1, "Extent")
                    elev_extent.attrib["name"] = "elevation"
                    elev_extent.attrib["default"] = "0"
                    try:
                        units = topology.variables["time"].units
                        if list_timesteps:
                            temptime = [netCDF4.num2date(topology.variables["time"][i], units).isoformat('T')+"Z" for i in xrange(topology.variables["time"].shape[0])]
                            time_extent.text = temptime.__str__().strip("[]").replace("'", "").replace(" ", "")
                        else:
                            time_extent.text = netCDF4.num2date(topology.variables["time"][0], units).isoformat('T') + "Z/" + netCDF4.num2date(topology.variables["time"][-1], units).isoformat('T') + "Z"
                    except:
                        time_extent.text = str(topology.variables["time"][0]) + "/" + str(topology.variables["time"][-1])
                    if nc.variables[variable].ndim > 2:
                        try:
                            ET.SubElement(layer1, "DepthLayers").text = str(range(nc.variables["siglay"].shape[0])).replace("[", "").replace("]", "")
                            elev_extent.text = str(range(nc.variables["siglay"].shape[0])).replace("[", "").replace("]", "")
                        except:
                            ET.SubElement(layer1, "DepthLayers").text = ""
                        try:
                            if nc.variables["siglay"].positive.lower() == "up":
                                ET.SubElement(layer1, "DepthDirection").text = "Down"
                            elif nc.variables["siglay"].positive.lower() == "down":
                                ET.SubElement(layer1, "DepthDirection").text = "Up"
                            else:
                                ET.SubElement(layer1, "DepthDirection").text = ""
                        except:
                            ET.SubElement(layer1, "DepthDirection").text = ""
                    else:
                        ET.SubElement(layer1, "DepthLayers").text = "0"
                        elev_extent.text = "0"
                        ET.SubElement(layer1, "DepthDirection").text = "Down"
                    if layertype == "*":
                        style = "composite"
                        #style_code = style + "_average_jet_None_None_" + location + "_False" TODO: no grid location
                        style_code = style + "_average_jet_None_None_None_False"
                        style = ET.SubElement(layer1, "Style")
                        ET.SubElement(style, "Name").text = style_code
                        ET.SubElement(style, "Title").text = style_code
                        ET.SubElement(style, "Abstract").text = "http://" + Site.objects.values()[0]['domain'] + "/doc"
                        legendurl = ET.SubElement(style, "LegendURL")
                        legendurl.attrib["width"] = "50"
                        legendurl.attrib["height"] = "80"
                        ET.SubElement(legendurl, "Format").text = "image/png"
                    elif layertype == "+":
                        for style in ["pcolor", "facets", "filledcontours", "contours"]:
                            #style_code = style + "_average_jet_None_None_" + location + "_False" # TODO: no grid location
                            style_code = style + "_average_jet_None_None_None_False"
                            style = ET.SubElement(layer1, "Style")
                            ET.SubElement(style, "Name").text = style_code
                            ET.SubElement(style, "Title").text = style_code
                            ET.SubElement(style, "Abstract").text = "http://" + Site.objects.values()[0]['domain'] + "/doc"
                            legendurl = ET.SubElement(style, "LegendURL")
                            legendurl.attrib["width"] = "50"
                            legendurl.attrib["height"] = "80"
                            ET.SubElement(legendurl, "Format").text = "image/png"
                    elif layertype == ",":
                        for style in ["vectors", "barbs", "pcolor", "facets", "filledcontours", "contours"]:
                            #style_code = style + "_average_jet_None_None_" + location + "_False" TODO: no grid location
                            style_code = style + "_average_jet_None_None_None_False"
                            style = ET.SubElement(layer1, "Style")
                            ET.SubElement(style, "Name").text = style_code
                            ET.SubElement(style, "Title").text = style_code
                            ET.SubElement(style, "Abstract").text = "http://" + Site.objects.values()[0]['domain'] + "/doc"
                            legendurl = ET.SubElement(style, "LegendURL")
                            legendurl.attrib["width"] = "50"
                            legendurl.attrib["height"] = "80"
                            ET.SubElement(legendurl, "Format").text = "image/png"
                #legend_onlineresource = ET.SubElement(legendurl, "OnlineResource")
                #legend_onlineresource.attrib["xlink:type"] = "simple"
                #legend_onlineresource.attrib["xlink:href"] = href
                #legend_onlineresource.attrib["xmlns:xlink"] = "http://www.w3.org/1999/xlink"
        if True:  # except:
            pass
    nc.close()
    tree = ET.ElementTree(root)
    try:
        if req.GET["FORMAT"].lower() == "text/javascript":
            import json
            output_dict = {}
            output_dict["capabilities"] = r'<?xml version="1.0" encoding="utf-8"?>' + ET.tostring(root)
            callback = "parseResponse"
            try:
                callback = request.GET["CALLBACK"]
            except:
                pass
            try:
                callback = request.GET["callback"]
            except:
                pass
            response = HttpResponse(content_type="text/javascript")
            output_str = callback + "(" + json.dumps(output_dict, indent=4, separators=(',', ': '), allow_nan=True) + ")"
            response.write(output_str)
        else:
            # Return the response
            response = HttpResponse(content_type="text/xml")
            response.write(r'<?xml version="1.0" encoding="utf-8"?>')
            tree.write(response)
    except:
        # Return the response
        response = HttpResponse(content_type="text/xml")
        response.write(r'<?xml version="1.0" encoding="utf-8"?>')
        tree.write(response)
    return response

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


