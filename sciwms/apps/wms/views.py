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
matplotlib.use("Agg")
from mpl_toolkits.basemap import Basemap
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg

# Other random "from" imports
from rtree import index as rindex
from collections import deque
from StringIO import StringIO  # will be deprecated in Python3, use io.byteIO instead

from django.conf import settings
from django.contrib.sites.models import Site
from django.template.loader import get_template
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth import authenticate, login, logout

from sciwms.libs.data import cgrid, ugrid
import sciwms.apps.wms.wms_requests as wms_reqs
from sciwms.apps.wms.models import Dataset, Server, Group, VirtualLayer
from sciwms.util import cf

import pyugrid
import numpy as np

output_path = os.path.join(settings.PROJECT_ROOT, 'logs', 'sciwms_wms.log')
# Set up Logger
logger = multiprocessing.get_logger()
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(output_path)
formatter = logging.Formatter(fmt='[%(asctime)s] - <<%(levelname)s>> - |%(message)s|')
handler.setFormatter(formatter)
logger.addHandler(handler)


def crossdomain(request):
    with open(os.path.join(settings.COMMON_STATIC_FILES, "common", "crossdomain.xml")) as f:
        response = HttpResponse(content_type="text/xml")
        response.write(f.read())
    return response


def datasets(request):
    
    try:
        js_obj = Dataset.objects.get(name='json_all')

        data = json.dumps(js_obj.json)
        if 'callback' in request.REQUEST:
            data = "{0}({1})".format(request.REQUEST['callback'], data)
        logger.info("Returning json_all object")
    except:
        from django.core import serializers
        datasets = Dataset.objects.all()
        data = serializers.serialize('json', datasets)
        logger.info("Returning serialized datasets.")
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.info(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    return HttpResponse(data, mimetype='application/json')


def grouptest(request, group):
    from django.template import Context
    sites = Site.objects.values()
    #print group
    group = Group.objects.get(name=group)
    dict1 = Context({ 'localsite' : sites[0]['domain'],
                      'datasets'  : list(Dataset.objects.filter(group=group))})
    return HttpResponse(get_template('wms/wms_openlayers_test.html').render(dict1))


def groups(request, group):
    import django.shortcuts as dshorts
    reqtype = None
    try:
        reqtype = request.GET['REQUEST']
    except:
        try:
            reqtype = request.GET['request']
        except:
            group = Group.objects.get(name=group)
            datasets = Dataset.objects.filter(group=group)
            for dataset in datasets:
                dataset.uri = dataset.path()
                if urlparse(dataset.uri).scheme != "":
                    # Used in template to linkify to URI
                    dataset.online = True
            context = { "datasets" : datasets }
            return dshorts.render_to_response('wms/index.html', context)
    if reqtype.lower() == "getcapabilities":  # Do GetCapabilities
        group = Group.objects.get(name=group)
        caps = wms_reqs.groupGetCapabilities(request, group, logger)
        return caps
    elif reqtype is not None:
        try:
            layers = request.GET["LAYERS"]
        except:
            layers = request.GET["layers"]
        dataset = layers.split("/")[0]
        request.GET = request.GET.copy()
        request.GET["LAYERS"] = layers.replace(dataset+"/", "")
        request.GET["layers"] = layers.replace(dataset+"/", "")
        return wms(request, dataset)


def index(request):
    import django.shortcuts as dshorts
    datasets = Dataset.objects.all()
    for dataset in datasets:
        dataset.uri = dataset.path()
        if urlparse(dataset.uri).scheme != "":
            # Used in template to linkify to URI
            dataset.online = True
    context = { "datasets" : datasets }
    return dshorts.render_to_response('wms/index.html', context)


def openlayers(request, filepath):
    return HttpResponse(get_template('wms/openlayers/%s' % filepath, content_type='text'))


def simpleclient(request):
    #grid_cache.check_topology_age()
    from django.template import Context
    sites = Site.objects.values()
    dict1 = Context({ 'localsite' : sites[0]['domain'],
                      'datasets'  : Dataset.objects.values()})
    return HttpResponse(get_template('wms/wms_openlayers_test.html').render(dict1))


def leafletclient(request):
    from django.template import Context
    sites = Site.objects.values()
    dict1 = Context({ 'localsite' : sites[0]['domain'],
                      'datasets'  : Dataset.objects.values()})
    return HttpResponse(get_template('wms/leaflet_example.html').render(dict1))


def authenticate_view(request):
    if request.user.is_authenticated():
        return True

    if request.method == 'POST':
        uname = request.POST.get('username', None)
        passw = request.POST.get('password', None)
    elif request.method == 'GET':
        uname = request.GET.get('username', None)
        passw = request.GET.get('password', None)

    user = authenticate(username=uname, password=passw)

    if user is not None and user.is_active:
        login(request, user)
        return True
    else:
        return False

def logout_view(request):
    logout(request)

def update_dataset(request, dataset):
    if authenticate_view(request):
        if dataset is None:
            return HttpResponse(json.dumps({ "message" : "Please include 'dataset' parameter in GET request." }), mimetype='application/json')
        else:
            d = Dataset.objects.get(name=dataset)
            d.update_cache()
            return HttpResponse(json.dumps({ "message" : "Scheduled" }), mimetype='application/json')
    else:
        return HttpResponse(json.dumps({ "message" : "Authentication failed, please login to the admin console first or pass login credentials to the GET request ('username' and 'password')" }), mimetype='application/json')
        
    logout_view(request)

def add(request):
    if authenticate_view(request):
        dataset_endpoint = request.POST.get("uri", None)
        dataset_id = request.POST.get("id", None)
        dataset_title = request.POST.get("title", None)
        dataset_abstract = request.POST.get("abstract", None)
        dataset_update = bool(request.POST.get("update", False))
        memberof_groups = request.POST.get("groups", None)
        if memberof_groups is None:
            memberof_groups = []
        else:
            memberof_groups = memberof_groups.split(",")
        if dataset_id is None:
            return HttpResponse("Exception: Please include 'id' parameter in POST request.", status=500)
        elif dataset_endpoint is None:
            return HttpResponse("Exception: Please include 'uri' parameter in POST request.", status=500)
        elif dataset_abstract is None:
            return HttpResponse("Exception: Please include 'abstract' parameter in POST request.", status=500)
        elif dataset_update is None:
            return HttpResponse("Exception: Please include 'update' parameter in POST request.", status=500)
        else:
            if len(list(Dataset.objects.filter(name=dataset_id))) > 0:
                dataset = Dataset.objects.get(name = dataset_id)
            else:
                dataset = Dataset.objects.create(name = dataset_id,
                                                 title = dataset_title,
                                                 abstract = dataset_abstract,
                                                 uri = dataset_endpoint,
                                                 keep_up_to_date = dataset_update)
                dataset.save()
            for groupname in memberof_groups:
                if len(list(Group.objects.filter(name = groupname))) > 0:
                    group = Group.objects.get(name = groupname)
                    dataset.groups.add(group)
                    dataset.save()
                return HttpResponse("Success: Dataset %s added to the server, and to %s groups." % (dataset_id, memberof_groups.__str__()))
    logout_view(request)


def add_to_group(request):
    if authenticate_view(request):
        dataset_id = request.GET.get("id", None)
        memberof_groups = request.GET.get("groups", None)
        if memberof_groups is None:
            memberof_groups = []
        else:
            memberof_groups = memberof_groups.split(",")
        if dataset_id is None:
            return HttpResponse("Exception: Please include 'id' parameter in POST request.", status=500)
        else:
            if len(list(Dataset.objects.filter(name=dataset_id))) > 0:
                dataset = Dataset.objects.get(name = dataset_id)
            else:
                return HttpResponse("Exception: Dataset matching that ID (%s) does not exist." % (dataset_id,), status=500)
            for groupname in memberof_groups:
                if len(list(Group.objects.filter(name = groupname))) > 0:
                    group = Group.objects.get(name = groupname)
                    dataset.groups.add(group)
                    dataset.save()
                return HttpResponse("Success: Dataset %s added to %s groups." % (dataset_id, memberof_groups.__str__()))
    logout_view(request)


def remove(request):
    if authenticate_view(request):
        dataset_id = request.GET.get("id", None)
        if dataset_id is None:
            return HttpResponse("Exception: Please include 'id' parameter in GET request.")
        else:
            dataset = Dataset.objects.get(name=dataset_id)
            dataset.delete()
            return HttpResponse("Dataset %s removed from this wms server." % dataset_id)
    else:
        return HttpResponse(json.dumps({ "message" : "authentication failed" }), mimetype='application/json')
    logout_view(request)


def remove_from_group(request):
    if authenticate_view(request):
        dataset_id = request.GET.get("id", None)
        memberof_groups = request.GET.get("groups", None)
        if memberof_groups is None:
            memberof_groups = []
        else:
            memberof_groups = memberof_groups.split(",")
            if dataset_id is None:
                return HttpResponse("Exception: Please include 'id' parameter in POST request.", status=500)
            else:
                if len(list(Dataset.objects.filter(name=dataset_id))) > 0:
                    dataset = Dataset.objects.get(name = dataset_id)
                else:
                    return HttpResponse("Exception: Dataset matching that ID (%s) does not exist." % (dataset_id,), status=500)
            for groupname in memberof_groups:
                if len(list(Group.objects.filter(name = groupname))) > 0:
                    group = Group.objects.get(name = groupname)
                    dataset.groups.remove(group)
                    dataset.save()
            return HttpResponse()
    logout_view(request)


def documentation(request):
    return HttpResponseRedirect('http://acrosby.github.io/sci-wms')


def lower_request(request):
    gettemp = request.GET.copy()
    for key in request.GET.iterkeys():
        gettemp[key.lower()] = request.GET[key]
    request._set_get(gettemp)
    return request


def database_request_interaction(request, dataset):
    if VirtualLayer.objects.filter(datasets__name = dataset):
        vlayer = VirtualLayer.objects.filter(datasets__name=dataset).filter(layer_expression = request.GET['layers'])
        request.GET['layers'] = vlayer[0].layer_expression
    return request


def wms(request, dataset):
    try:
        request = lower_request(request)
        reqtype = request.GET['request']
        if reqtype.lower() == 'getmap':
            request = database_request_interaction(request, dataset)
            import sciwms.apps.wms.wms_handler as wms
            handler = wms.wms_handler(request)
            action_request = handler.make_action_request(request)
            if action_request is not None:
                response = getMap(action_request, dataset)
            else:
                response = HttpResponse()
        elif reqtype.lower() == 'getfeatureinfo':
            response = getFeatureInfo(request, dataset)
        elif reqtype.lower() == 'getlegendgraphic':
            response = getLegendGraphic(request, dataset)
        elif reqtype.lower() == 'getcapabilities':
            response = getCapabilities(request, dataset)
        logger.info(str(request.GET))
        return response
    except Exception:
        raise
        exc_type, exc_value, exc_traceback = sys.exc_info()
        str_exc_descr = repr(traceback.format_exception(exc_type, exc_value, exc_traceback)) + '\n' + str(request)
        logger.error("Status 500 Error: " + str_exc_descr)
        return HttpResponse("<pre>Error: " + str_exc_descr + "</pre>", status=500)


def getCapabilities(req, dataset):  # TODO move get capabilities to template system like sciwps
    """
    get capabilities document based on this getcaps:


    http://coastmap.com/ecop/wms.aspx?service=WMS&version=1.1.1&request=getcapabilities

    """
    # Create the object to be encoded to xml later
    root = ET.Element('WMT_MS_Capabilities')
    root.attrib["version"] = "1.1.1"
    href = "http://" + Site.objects.values()[0]['domain'] + "/wms/" + dataset + "/?"
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
    ET.SubElement(layer, "Title").text      = Dataset.objects.get(name=dataset).title
    ET.SubElement(layer, "Abstract").text   = Dataset.objects.get(name=dataset).abstract
    ET.SubElement(layer, "SRS").text        = "EPSG:3857"
    ET.SubElement(layer, "SRS").text        = "MERCATOR"
    nc = netCDF4.Dataset(Dataset.objects.get(name=dataset).path())
    topology = netCDF4.Dataset(os.path.join(settings.TOPOLOGY_PATH, dataset + '.nc'))
    list_timesteps = Dataset.objects.get(name=dataset).display_all_timesteps
    for variable in nc.variables.keys():
        try:
            location = nc.variables[variable].location
        except:
            if topology.grid != 'False':
                location = "grid"
            else:
                location = "node"
        if location == "face":
            location = "cell"
        if True:
            #nc.variables[variable].location
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
            templon = topology.variables["lon"][:]
            templat = topology.variables["lat"][:]
            #templon = templon[not numpy.isnan(templon)]
            #templat = templat[not numpy.isnan(templat)]
            llbbox.attrib["minx"] = str(numpy.nanmin(templon))
            llbbox.attrib["miny"] = str(numpy.nanmin(templat))
            llbbox.attrib["maxx"] = str(numpy.nanmax(templon))
            llbbox.attrib["maxy"] = str(numpy.nanmax(templat))
            #llbbox.attrib["minx"] = str(templon.min())
            #llbbox.attrib["miny"] = str(templat.min())
            #llbbox.attrib["maxx"] = str(templon.max())
            #llbbox.attrib["maxy"] = str(templat.max())
            llbbox = ET.SubElement(layer1, "BoundingBox")
            llbbox.attrib["SRS"] = "EPSG:4326"
            #llbbox.attrib["minx"] = str(templon.min())
            #llbbox.attrib["miny"] = str(templat.min())
            #llbbox.attrib["maxx"] = str(templon.max())
            #llbbox.attrib["maxy"] = str(templat.max())
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
                try:
                    units = topology.variables["time"].units
                #print units
                #print topology.variables["time"][0], len(topology.variables["time"])
                #print topology.variables["time"][-1]
                    if len(topology.variables["time"]) == 1:
                        time_extent.text = netCDF4.num2date(topology.variables["time"][0], units).isoformat('T') + "Z"
                    else:
                        if list_timesteps:
                            temptime = [netCDF4.num2date(topology.variables["time"][i], units).isoformat('T')+"Z" for i in xrange(topology.variables["time"].shape[0])]
                            time_extent.text = temptime.__str__().strip("[]").replace("'", "").replace(" ", "")
                        else:
                            time_extent.text = netCDF4.num2date(topology.variables["time"][0], units).isoformat('T') + "Z/" + netCDF4.num2date(topology.variables["time"][-1], units).isoformat('T') + "Z"
                except:
                    if len(topology.variables["time"]) == 1:
                        time_extent.text = str(topology.variables["time"][0])
                    else:
                        time_extent.text = str(topology.variables["time"][0]) + "/" + str(topology.variables["time"][-1])
            except:
                pass
            ## Listing all available elevation layers is a tough thing to do for the range of types of datasets...
            if topology.grid.lower() == 'false':
                if nc.variables[variable].ndim > 2:
                    try:
                        ET.SubElement(layer1, "DepthLayers").text = str(range(nc.variables["siglay"].shape[0])).replace("[", "").replace("]", "").replace(" ", "")
                        elev_extent.text = str(range(nc.variables["siglay"].shape[0])).replace("[", "").replace("]", "").replace(" ", "")
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
                    ET.SubElement(layer1, "DepthDirection").text = "Down"
                    elev_extent.text = "0"
            elif topology.grid.lower() == 'cgrid':
                if nc.variables[variable].ndim > 3:
                    try:
                        ET.SubElement(layer1, "DepthLayers").text = str(range(nc.variables[variable].shape[1])).replace("[", "").replace("]", "").replace(" ", "")
                        elev_extent.text = str(range(nc.variables[variable].shape[1])).replace("[", "").replace("]", "").replace(" ", "")
                    except:
                        ET.SubElement(layer1, "DepthLayers").text = ""
                    try:
                        #if nc.variables["depth"].positive.lower() == "up":
                        #    ET.SubElement(layer1, "DepthDirection").text = "Down"
                        #elif nc.variables["depth"].positive.lower() == "down":
                        #    ET.SubElement(layer1, "DepthDirection").text = "Up"
                        #else:
                        #    ET.SubElement(layer1, "DepthDirection").text = ""
                        ET.SubElement(layer1, "DepthDirection").text = ""
                    except:
                        ET.SubElement(layer1, "DepthDirection").text = ""
                else:
                    ET.SubElement(layer1, "DepthLayers").text = "0"
                    ET.SubElement(layer1, "DepthDirection").text = "Down"
                    elev_extent.text = "0"
            else:
                ET.SubElement(layer1, "DepthLayers").text = "0"
                ET.SubElement(layer1, "DepthDirection").text = "Down"
                elev_extent.text = "0"
            ##

            for style in ["filledcontours", "contours", "pcolor", "facets"]:
                style_code = style + "_average_jet_None_None_" + location + "_False"
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
                    try:
                        location = nc.variables[variable].location
                    except:
                        if topology.grid != 'False':
                            location = "grid"
                        else:
                            location = "node"
                    if location == "face":
                        location = "cell"
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
                        style_code = style + "_average_jet_None_None_" + location + "_False"
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
                            style_code = style + "_average_jet_None_None_" + location + "_False"
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
                            style_code = style + "_average_jet_None_None_" + location + "_False"
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
    try:
        units = nc.variables[variables[0]].units
    except:
        units = ''
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
        cb.set_label(units)
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
            logger.info( str((levels, levs)) )
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


def getFeatureInfo(request, dataset):
    """
     /wms/GOM3/?ELEVATION=1&LAYERS=temp&FORMAT=image/png&TRANSPARENT=TRUE&STYLES=facets_average_jet_0_32_node_False&SERVICE=WMS&VERSION=1.1.1&REQUEST=GetFeatureInfo&SRS=EPSG:3857&BBOX=-7949675.196111,5078194.822174,-7934884.63114,5088628.476533&X=387&Y=196&INFO_FORMAT=text/csv&WIDTH=774&HEIGHT=546&QUERY_LAYERS=salinity&TIME=2012-08-14T00:00:00/2012-08-16T00:00:00
    """
    from datetime import date
    from mpl_toolkits.basemap import pyproj
    X = float(request.GET['x'])
    Y = float(request.GET['y'])
    box = request.GET["bbox"]
    box = box.split(",")
    latmin = float(box[1])
    latmax = float(box[3])
    lonmin = float(box[0])
    lonmax = float(box[2])
    height = float(request.GET["height"])
    width = float(request.GET["width"])
    styles = request.GET["styles"].split(",")[0].split("_")
    QUERY_LAYERS = request.GET['query_layers'].split(",")

    # BM 20140731
    # QUERY_LAYERS expects the "UI" name which is then mapped to a CF standard_name and the variable is looked up via its standard_name using the CF util

    try:
        elevation = int(request.GET['elevation'])
    #print elevation
    except:
        elevation = 0

    mi = pyproj.Proj("+proj=merc +lon_0=0 +k=1 +x_0=0 +y_0=0 +a=6378137 +b=6378137 +units=m +no_defs ")
    # Find the gfi position as lat/lon, assumes 0,0 is ul corner of map

    # target longitude, target latitude
    tlon, tlat = mi(lonmin+((lonmax-lonmin)*(X/width)), latmax-((latmax-latmin)*(Y/height)), inverse=True)
    lonmin, latmin = mi(lonmin, latmin, inverse=True)
    lonmax, latmax = mi(lonmax, latmax, inverse=True)

    # want data at (tlon,tlat)

    # outline
    # 1) use topology to get lat/lon values: this uses pyugrid for UGRID compliant datasets
    # 2) get index of "node" that is closest to the requested point
    #    NOTE: node is more meaningful in UGRID, but is also created for each grid point in structured grids


    ugrid = False # flag to track if UGRID file is found
    # ------------------------------------------------------------------------------------------------------------UGRID
    # pyugrid to handle UGRID topology
    try:

        topology_path = os.path.join(settings.TOPOLOGY_PATH, dataset + '.nc')
        logger.info("Trying to load pyugrid cache {0}".format(dataset))
        ug = pyugrid.UGrid.from_ncfile(topology_path)
        logger.info("Loaded pyugrid cache")

        # UGRID variables
        lon = ug.nodes[:,0]
        lat = ug.nodes[:,1]
        nv  = ug.faces[:]

        # rindex, create if none exists yet
        nodes_path = os.path.join(settings.TOPOLOGY_PATH, dataset + '_nodes')
        if os.path.exists(nodes_path+'.dat') and os.path.exists(nodes_path+'.idx'):
            tree = rindex.Index(nodes_path)
            logger.info('UGRID node index found %s' % nodes_path)
        else:
            def generator_nodes():
                for i, c in enumerate(zip(lon, lat, lon, lat)):
                    yield(i, c, None)
            logger.info('UGRID indexing nodes %s' % nodes_path)
            tree = rindex.Index(nodes_path, generator_nodes(), overwrite=True)
            logger.info('UGRID nodes indexed')

        # find closest node or cell (only doing node for now)
        nindex = list(tree.nearest((tlon, tlat, tlon, tlat), 1, objects=True))[0]
        selected_longitude, selected_latitude = tuple(nindex.bbox[:2])
        index = nindex.id # single value (node index)
        tree.close()
        # this is UGRID
        ugrid = True
    
    # ------------------------------------------------------------------------------------------------------------ Not pyUGRID
    except: # default to previous workflow for non UGRID
        # structured grids (where 'nodes' are the structured points)
        topology = netCDF4.Dataset(os.path.join(settings.TOPOLOGY_PATH, dataset + '.nc'))
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

    url = Dataset.objects.get(name=dataset).path()
    datasetnc = netCDF4.Dataset(url)

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
        v = cf.map.get(var, None)
        if v == None:
            logger.warning('requested QUERY_LAYER %s, no map exists to CF standard_name' % var)
            continue
        variable = cf.get_by_standard_name(datasetnc, v['standard_name'])
        try:
            units = variable.units
        except:
            units = ""
        values = getvar(variable, time, elevation, index)
        logger.info('appending (variable,units,values) = (%s,%s,:) with CF standard_name %s' % (var,units,v['standard_name']))
        varis.append((var, units, values))

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


def getMap(request, dataset):
    '''
    the meat and bones of getMap
    '''
    from mpl_toolkits.basemap import pyproj
    from matplotlib.figure import Figure

    #output_path = os.path.join(config.fullpath_to_wms, 'src', 'pywms', 'sciwms_wms')
    # Set up Logger
    #logger = multiprocessing.get_logger()
    #logger.setLevel(logging.ERROR)
    #handler = logging.FileHandler('%s.log' % output_path)
    #formatter = logging.Formatter(fmt='[%(asctime)s] - <<%(levelname)s>> - |%(message)s|')
    #handler.setFormatter(formatter)
    #logger.addHandler(handler)

# ----------------------------------------------
# some shared methods used many places in getMap
    def blank_response(width, height, dpi=5):
        """
        return a transparent (blank) response
        used for tiles with no intersection with the current view or for some other error.
        """
        fig = Figure(dpi=dpi, facecolor='none', edgecolor='none')
        fig.set_alpha(0)
        ax = fig.add_axes([0, 0, 1, 1])
        #I don't know why height and width is divided by dpi,
        #this is left over from old sciwms code
        #maybe response needs to be in units of inches?
        fig.set_figheight(height/dpi)
        fig.set_figwidth(width/dpi)
        ax.set_frame_on(False)
        ax.set_clip_on(False)
        ax.set_position([0, 0, 1, 1])
        canvas = FigureCanvasAgg(fig)
        response = HttpResponse(content_type='image/png')
        canvas.print_png(response)
        return response

# ----------------------------------------------


    #totaltimer = timeobj.time()
    #loglist = []

    # direct the service to the dataset
    url = Dataset.objects.get(name=dataset).path()

    # Get the size of image requested and the geographic extent in webmerc
    width = float(request.GET["width"])
    height = float(request.GET["height"])
    latmax = float(request.GET["latmax"])
    latmin = float(request.GET["latmin"])
    lonmax = float(request.GET["lonmax"])
    lonmin = float(request.GET["lonmin"])

    # Get time extents, elevation index(layer), and styles(actions)
    datestart = request.GET["datestart"]
    dateend = request.GET["dateend"]

    # BM: buyer beware, this is actually WMS 'ELEVATION', AKA z coordinate, NOT WMS 'LAYERS'
    # TODO: find closest vertical index, for now, just zero
    layer = [0]
    '''
    layer = request.GET["layer"]
    layer = layer.split(",")
    for i, l in enumerate(layer):
    #    layer[i] = int(l)-1
        layer = int(l)
    layer = numpy.asarray(layer)
    '''

    actions = request.GET["actions"]
    actions = set(actions.split(","))

    # Get the colormap requested, the color limits/scaling
    colormap = request.GET["colormap"]
    if request.GET["climits"][0] != "None":
        climits = [float(lim) for lim in request.GET["climits"]]
    else:
        climits = ["None", "None"]

    # Get the absolute magnitude bool, the topological location of variable of
    # interest, and the variables of interest (comma sep, no spaces, limit 2)
    magnitude = request.GET["magnitude"]
    topology_type = request.GET["topologytype"]
    variables = request.GET["variables"].split(",") # NOTE: this 'variables' is actually WMS LAYERS, see wms_handler
    continuous = False

    # Get the box coordinates from webmercator to proper lat/lon for grid subsetting
    mi = pyproj.Proj("+proj=merc +lon_0=0 +k=1 +x_0=0 +y_0=0 +a=6378137 +b=6378137 +units=m +no_defs ")
    lonmin, latmin = mi(lonmin, latmin, inverse=True)
    lonmax, latmax = mi(lonmax, latmax, inverse=True)
    logger.debug("getMap Subset Bounding Box: {0}, {1}, {2}, {3}".format(lonmin,latmin,lonmax,latmax))

    try:
        #THIS IS ADDED BY BRANDON TO ADD SUPPORT FOR PYUGRID!!!!
        
        #THESE SHOULD BE SOMEHWERE ELSE JUST IN A RUSH NOW
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
                times = nc.variables['time'][:]
                datestart = datetime.datetime.strptime(datestart, "%Y-%m-%dT%H:%M:%S" )
            
                # datetime obj --> netcdf datenum
                datestart = round(netCDF4.date2num(datestart, units=nc.variables['time'].units))  
                logger.info("datestart = {0}".format(datestart))

                #bisect_right returns the index that would maintain sorted order if
                #the element (in this case datestart) was inserted to the right of an element
                time = bisect.bisect_right(times,datestart)

                #goal is to find closest time index, or do we always use the "one before" or "one after"?            
                #This mod will get the nearest element by checking the one after vs. the one before
                if time == len(times):
                    time -= 1
                elif time != 0:
                    time = time if abs(times[time]-datestart) < abs(time[time-1]-datestart) else time-1
            except:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logger.info("Dataset doesn't contain temporal dimension: "
                            + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            finally:
                del times
            
            return time

        def tricontourf_response(triang_subset,
                                 data,
                                 lonmin,
                                 latmin,
                                 lonmax,
                                 latmax,
                                 width,
                                 height,
                                 dpi=80.0,
                                 nlvls = 15):
            
            logger.info("tricontourf: [lonmin = {0},latmin = {1}, lonmax = {2}, latmax = {3}]".format(lonmin,latmin,lonmax,latmax))
            projection = request.GET["projection"]
            logger.info("projection={0}".format(projection))

            if projection == 'merc':
                proj = mi #alex's default mercator projection object
            else:
                logger.error("Unsupported Projction: {0}".format(proj))
            
            fig = Figure(dpi=dpi, facecolor='none', edgecolor='none')
            fig.set_alpha(0)
            fig.set_figheight(height/dpi)
            fig.set_figwidth(width/dpi)

            ax = fig.add_axes([0., 0., 1., 1.], xticks=[], yticks=[])
            ax.set_axis_off()

            lvls = np.linspace(data.min(), data.max(), nlvls)

            logger.info("Computing mercator projection.")
            triang_subset.x, triang_subset.y = proj(triang_subset.x, triang_subset.y)
            logger.info("Done computing mercator projection.")
            logger.info("triang_subset.x.shape = {0}".format(triang_subset.x.shape))
            logger.info("triang_subset.y.shape = {0}".format(triang_subset.y.shape))
            logger.info("triang_subset.x[:10] = {0}".format(triang_subset.x[:10]))

            ax.tricontourf(triang_subset, data, levels=lvls)

            merclatmax = float(request.GET["latmax"])
            merclatmin = float(request.GET["latmin"])
            merclonmax = float(request.GET["lonmax"])
            merclonmin = float(request.GET["lonmin"])

            logger.info("request_llcrnr = {0}".format((merclonmin,merclatmin)))
            logger.info("request_upcrnr = {0}".format((merclonmax,merclatmax)))
                        
            ax.set_xlim(merclonmin, merclonmax)
            ax.set_ylim(merclatmin, merclatmax)

            ax.set_frame_on(False)
            ax.set_clip_on(False)
            ax.set_position([0, 0, 1, 1])
            
            plt.axis('off')

            canvas = FigureCanvasAgg(fig)
            response = HttpResponse(content_type='image/png')
            canvas.print_png(response)
            return response

        def ugrid_quiver_response(lon, lat, dx, dy, lonmin, latmin, lonmax, latmax, width, height, dpi=80):
            # fig = Figure(dpi=dpi, facecolor='none', edgecolor='none')
            # fig.set_alpha(0)
            # fig.set_figheight(height/dpi)
            # fig.set_figwidth(width/dpi)
            import cartopy.crs as ccrs
            fig = Figure(dpi=dpi, facefolor='none',edgecolor='none')
            # fig, ax = plt.subplots(dpi=dpi, facecolor='none', edgecolor='none')
            fig.set_alpha(0)
            
            fig.set_figheight(height/dpi)
            fig.set_figwidth(width/dpi)
            projection = request.GET["projection"]
            # m = Basemap(llcrnrlon=lonmin, llcrnrlat=latmin,
            #             urcrnrlon=lonmax, urcrnrlat=latmax, projection=projection,
            #             resolution=None,
            #             lat_ts = 0.0,
            #             suppress_ticks=True)
            ax =  fig.add_axes([0,0,1,1],xticks=[],yticks=[],projection=ccrs.Mercator())
            # m.ax = fig.add_axes([0, 0, 1, 1], xticks=[], yticks=[])
            
            #plot unit vectors
            mags = np.sqrt(dx**2 + dy**2)
            m.ax.quiver(lon, lat, dx/mags, dy/mags, mags)

            logger.info("mags.shape = {0}".format(mags.shape))
            logger.info("quiver plotted.")
            m.ax.set_xlim(lonmin, lonmax)
            m.ax.set_ylim(latmin, latmax)
            m.ax.set_frame_on(False)
            m.ax.set_clip_on(False)
            m.ax.set_position([0, 0, 1, 1])
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

        
        # actual try block starts here (def methods only above)
        import matplotlib.tri as Tri

        topology_path = os.path.join(settings.TOPOLOGY_PATH, dataset + '.nc')
        logger.info("Trying to load pyugrid cache {0}".format(dataset))
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
            return blank_response(width, height);

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

            var = variables[0] # because it comes in as list, just using var for consistency with getFeatureInfo
            # get Variable using CF standard_name attribute
            v = cf.map.get(var, None)
            if v == None:
                logger.warning('requested LAYERS %s, no map exists to CF standard_name' % var)
                return blank_response(width, height) # was continue
            variable = cf.get_by_standard_name(datasetnc, v['standard_name'])

            logger.info('getMap retrieving LAYER %s with standard_name %s' % (var, v['standard_name']))

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
                return blank_response(width, height)
            
            logger.info("getMap finished retrieving variable {0}, serving tricontourf response".format(variables)) # TODO this logger statement (variables is list?)
            response = tricontourf_response(triang_subset, data, lonmin, latmin, lonmax, latmax, width, height)

        # vector
        elif len(variables) == 2:

            logger.info("len(variables) == 2")

            # get Variable using CF standard_name attribute (LIST)
            v = [cf.map.get(var, None) for var in variables]
            if None in v:
                logger.warning('requested LAYERS {0}, no map exists to CF standard_name for at least one of these'.format(variables))
                return blank_response(width, height) # was continue
            variable = map(lambda x: cf.get_by_standard_name(datasetnc, x['standard_name']), v)

            if None in variable:
                logger.warning('variable not found for at least these'.format(variables))
                return blank_response(width, height) # was continue

            logger.info("getMap retrieving variables {0}".format(variables))
            logger.info("time = {0}".format(time))

            # UGRID data has momentum (u,v) either on node (AKA vertices, eg. ADCIRC) or face (AKA triangle, eg. FVCOM/SELFE)
            #     check the location attribute of the UGRID variable to determine which lon/lat to use (if face, need a different set)
            location = set([v.__dict__.get('location', None) for v in variable])
            if len(location) > 1:
                logger.info("UGRID vector component variables require same 'location' attribute")
                return blank_response(width, height)
            
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
                    return blank_response(width, height)

            logger.info("len(data) = {0}".format(len(data)))
            logger.info("data[0].shape = {0}".format(data[0].shape))
            logger.info("data[1].shape = {0}".format(data[1].shape))
            response = ugrid_quiver_response(
                lon[sub_idx], lat[sub_idx], data[0][sub_idx], data[1][sub_idx],
                lonmin, latmin, lonmax, latmax, width, height)

            # response = \
            #     layered_quiver_response(lon,
            #                             lat,
            #                             triang_subset,
            #                             sub_idx,
            #                             data[0],
            #                             data[1],
            #                             lonmin,
            #                             latmin,
            #                             lonmax,
            #                             latmax,
            #                             width,
            #                             height)
        else:
            #don't know how to handle more than 2 variables
            logger.info("Cannot handle more than 2 variables per request.")
            return blank_response(width, height)

        # topology.close()
        datasetnc.close()
        
    except:

        # log reason we dropped to this OLD code section, indicates some exception from pyugrid, lets just record why
        logger.debug("IN EXCEPT!!!")
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.info("Something went wrong with pyugrid plot: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))

#---------
        # lets get some support functions (probably copied verbatim from above and can be reduced to one) to index the target data
        def get_lat_lon_subset_idx(lon,lat,lonmin,latmin,lonmax,latmax,padding=0.18):
            """
            A function to return the indicies of lat, lon within a bounding box.
            """
            return np.asarray(np.where(
                (lat <= (latmax + padding)) & (lat >= (latmin - padding)) &
                (lon <= (lonmax + padding)) & (lon >= (lonmin - padding)),)).squeeze()

        def contourf_response(lon_subset, lat_subset, data, lonmin, latmin, lonmax, latmax, width, height, dpi=80, nlvls = 15):
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
            lvls = np.linspace(data.min(), data.max(), nlvls)
            logger.info("lvls.shape = {0}, lvls.min() = {1}, lvls.max() = {2}".format(lvls.shape, lvls.min(), lvls.max()))
            m.ax.contourf(lon_subset, lat_subset, data, levels=lvls)
            m.ax.set_xlim(lonmin, lonmax)
            m.ax.set_ylim(latmin, latmax)
            m.ax.set_frame_on(False)
            m.ax.set_clip_on(False)
            m.ax.set_position([0, 0, 1, 1])
            canvas = FigureCanvasAgg(fig)
            response = HttpResponse(content_type='image/png')
            canvas.print_png(response)
            return response

        def quiver_response(lon, lat, dx, dy, lonmin, latmin, lonmax, latmax, width, height, dpi=80):
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

            #plot unit vectors
            mags = np.sqrt(dx**2 + dy**2)
            m.ax.quiver(lon, lat, dx/mags, dy/mags, mags)

            logger.info("mags.shape = {0}".format(mags.shape))
            logger.info("quiver plotted.")
            m.ax.set_xlim(lonmin, lonmax)
            m.ax.set_ylim(latmin, latmax)
            m.ax.set_frame_on(False)
            m.ax.set_clip_on(False)
            m.ax.set_position([0, 0, 1, 1])
            canvas = FigureCanvasAgg(fig)
            response = HttpResponse(content_type='image/png')
            canvas.print_png(response)
            return response

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
            return blank_response(width, height);

        # TEMPORAL SUBSET
        times = topology.variables['time'][:]
        datestart = datetime.datetime.strptime(datestart, "%Y-%m-%dT%H:%M:%S" )  # datestr --> datetime obj
        datestart = round(netCDF4.date2num(datestart, units=topology.variables['time'].units))  # datetime obj --> netcdf datenum
        time = bisect.bisect_right(times, datestart) - 1
        if settings.LOCALDATASET:
            time = [1]
        elif time == -1:
            time = [0]
        else:
            time = [time]
        if dateend != datestart:
            dateend = datetime.datetime.strptime( dateend, "%Y-%m-%dT%H:%M:%S" )  # datestr --> datetime obj
            dateend = round(netCDF4.date2num(dateend, units=topology.variables['time'].units))  # datetime obj --> netcdf datenum
            time.append(bisect.bisect_right(times, dateend) - 1)
            if settings.LOCALDATASET:
                time[1] = 1
            elif time[1] == -1:
                time[1] = 0
            else:
                time[1] = time[1]
            time = range(time[0], time[1]+1)


        # some short names for indexes
        t = time[0]  # TODO: ugh this is bad
        z = layer[0]

        # scalar
        if len(variables) == 1:

            logger.info("[non-UGRID] len(variables) == 1")

            var = variables[0] # because it comes in as list, just using var for consistency with getFeatureInfo
            # get Variable using CF standard_name attribute
            v = cf.map.get(var, None)
            if v == None:
                logger.warning('requested LAYERS %s, no map exists to CF standard_name' % var)
                return blank_response(width, height) # was continue
            variable = cf.get_by_standard_name(datasetnc, v['standard_name'])

            if variable is None:
                logger.warning('requested LAYERS %s, standard_name %s does not exist in datasete' % (var,v['standard_name']))
                return blank_response(width, height) # was continue

            logger.info('getMap retrieving LAYER %s with standard_name %s' % (var, v['standard_name']))

            # subset lon/lat and the data (should be the same size)
            lon_subset = getvar(cf.get_by_standard_name(datasetnc, 'longitude'), t, z, sub_idx)
            lat_subset = getvar(cf.get_by_standard_name(datasetnc, 'latitude'), t, z, sub_idx)
            data_subset = getvar(variable, t, z, sub_idx)

            logger.info("lon_subset.shape = {0}".format(lon_subset.shape))
            logger.info("lat_subset.shape = {0}".format(lat_subset.shape))
            logger.info("data_subset.shape = {0}".format(data_subset.shape))

            logger.info("getMap [non-UGRID] finished retrieving variable {0}, serving contourf response".format(variables)) # TODO this logger statement (variables is list?)
            response = contourf_response(lon_subset, lat_subset, data_subset, lonmin, latmin, lonmax, latmax, width, height)

        # vector
        elif len(variables) == 2:

            logger.info("[non-UGRID] len(variables) == 2")

            # get Variable using CF standard_name attribute (LIST)
            v = [cf.map.get(var, None) for var in variables]
            if None in v:
                logger.warning('requested LAYERS {0}, no map exists to CF standard_name for at least one of these'.format(variables))
                return blank_response(width, height) # was continue

            variable = map(lambda x: cf.get_by_standard_name(datasetnc, x['standard_name']), v)
            if None in variable:
                logger.warning('requested LAYERS %s, standard_name %s does not exist in datasete' % (var,v['standard_name']))
                return blank_response(width, height) # was continue

            logger.info("getMap retrieving variables {0}".format(variables))
            logger.info("time = {0}".format(time))

            # subset lon/lat and the data (should be the same size)
            lon_subset = getvar(cf.get_by_standard_name(datasetnc, 'longitude'), t, z, sub_idx)
            lat_subset = getvar(cf.get_by_standard_name(datasetnc, 'latitude'), t, z, sub_idx)
            u_subset = getvar(variable[0], t, z, sub_idx)
            v_subset = getvar(variable[1], t, z, sub_idx)
            
            logger.info("lon_subset.shape = {0}".format(lon_subset.shape))
            logger.info("lat_subset.shape = {0}".format(lat_subset.shape))
            logger.info("u_subset.shape = {0}".format(u_subset.shape))
            logger.info("v_subset.shape = {0}".format(v_subset.shape))

            logger.info("getMap [non-UGRID] finished retrieving variable {0}, serving quiver response".format(variables)) # TODO this logger statement (variables is list?)
            response = quiver_response(lon_subset, lat_subset, u_subset, v_subset, lonmin, latmin, lonmax, latmax, width, height)

        # bad request, more than 2 vars (or none)
        else:
            #don't know how to handle more than 2 variables
            logger.info("Cannot handle more than 2 variables per request.")
            return blank_response(width, height)


        '''
        # Get the data and appropriate resulting shape from the data source
        index = numpy.asarray(index)
        # we need to get var using cf.map and standard_name
        var1, var2 = cgrid.getvar(datasetnc, t, layer, variables, index)

        # Setup the basemap/matplotlib figure
        fig = Figure(dpi=80, facecolor='none', edgecolor='none')
        fig.set_alpha(0)
        projection = request.GET["projection"]
        m = Basemap(llcrnrlon=lonmin, llcrnrlat=latmin,
                    urcrnrlon=lonmax, urcrnrlat=latmax, projection=projection,
                    resolution=None,
                    lat_ts = 0.0,
                    suppress_ticks=True)
        m.ax = fig.add_axes([0, 0, 1, 1], xticks=[], yticks=[])
        try:  # Fail gracefully if not standard_name, should do this a little better than a try
            if 'direction' in datasetnc.variables[variables[1]].standard_name:
                #assign new var1,var2 as u,v components
                var2 = 450 - var2
                var2[var2 > 360] = var2[var2 > 360] - 360
                origvar2 = var2
                var2 = numpy.sin(numpy.radians(origvar2)) * var1  # var 2 needs to come first so that
                var1 = numpy.cos(numpy.radians(origvar2)) * var1  # you arn't multiplying by the wrong var1 val
        except:
            pass

        # Close remote dataset and local cache
        topology.close()
        datasetnc.close()

        if (climits[0] == "None") or (climits[1] == "None"):
            if magnitude.lower() == "log":
                CNorm = matplotlib.colors.LogNorm()
            else:
                CNorm = matplotlib.colors.Normalize()
        else:
            if magnitude.lower() == "log":
                CNorm = matplotlib.colors.LogNorm(vmin=climits[0],
                                                  vmax=climits[1],
                                                  clip=True,
                                                 )
            else:
                CNorm = matplotlib.colors.Normalize(vmin=climits[0],
                                                    vmax=climits[1],
                                                    clip=True,
                                                   )
        # Plot to the projected figure axes!
        if gridtype == 'cgrid':
            lon, lat = m(lon, lat)
            cgrid.plot(lon, lat, var1, var2, actions, m.ax, fig,
                       aspect = m.aspect,
                       height = height,
                       width = width,
                       norm = CNorm,
                       cmin = climits[0],
                       cmax = climits[1],
                       magnitude = magnitude,
                       cmap = colormap,
                       basemap = m,
                       lonmin = lonmin,
                       latmin = latmin,
                       lonmax = lonmax,
                       latmax = latmax,
                       projection = projection)
        lonmax, latmax = m(lonmax, latmax)
        lonmin, latmin = m(lonmin, latmin)
        m.ax.set_xlim(lonmin, lonmax)
        m.ax.set_ylim(latmin, latmax)
        m.ax.set_frame_on(False)
        m.ax.set_clip_on(False)
        m.ax.set_position([0, 0, 1, 1])
        canvas = FigureCanvasAgg(fig)
        response = HttpResponse(content_type='image/png')
        canvas.print_png(response)
        '''

    gc.collect()

    return response
