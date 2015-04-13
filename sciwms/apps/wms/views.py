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

@author: @acrosby, @brianmckenna
'''

import json
import logging
import netCDF4
import pyugrid
import re
import sys
import traceback
import multiprocessing
from urlparse import urlparse

from django.conf import settings
from django.contrib.sites.models import Site
from django.template import RequestContext
from django.template.loader import get_template
import django.http
from django.http import HttpResponse, HttpResponseRedirect
import django.contrib.auth
#from django.contrib.auth import authenticate, login, logout
from django.core.exceptions import ObjectDoesNotExist
import django.shortcuts
from django.views.decorators.http import require_POST

from sciwms.apps.wms.models import Dataset, Server, Group, VirtualLayer

from sciwms.util import cf, meta
from sciwms.libs.data.caching import update_dataset_cache


from .get_map import getMap
from .get_feature_info import getFeatureInfo
from .get_capabilities import getCapabilities

logger = multiprocessing.get_logger()

# TODO: update
def datasets(request):
    '''
    JSON datasets - for clients who do not want to use GetCapabilities
    '''
    data = []
    datasets = Dataset.objects.all().order_by('name')
    for dataset in datasets:
        d = json.loads(dataset.json)
        d['url'] = dataset.uri+'.html'
        data.append({dataset.name: d})
    return HttpResponse(json.dumps(data), mimetype='application/json')

def index(request):
    '''
    default view - list of available datasets
    '''
    import django.shortcuts
    datasets = Dataset.objects.all().order_by('name')
    for dataset in datasets:
        dataset.uri = dataset.path()
        if urlparse(dataset.uri).scheme != "":
            # Used in template to linkify to URI
            dataset.online = True
    context = { 'datasets': datasets }
    return django.shortcuts.render_to_response('wms/index.html', context, context_instance=RequestContext(request))

def documentation(request):
    return HttpResponseRedirect('http://asascience-open.github.io/sci-wms/')

def demo(request):
    context = { 'datasets'  : Dataset.objects.all()}
    return django.shortcuts.render_to_response('wms/demo.html', context, context_instance=RequestContext(request))


# authentication
def login(request):
    # TODO: POST only?
    if request.method == 'POST':
        username = request.POST.get('username', None)
        password = request.POST.get('password', None)
    elif request.method == 'GET':
        username = request.GET.get('username', None)
        password = request.GET.get('password', None)
    user = django.contrib.auth.authenticate(username=username, password=password)
    if user is not None:
        if user.is_active:
            django.contrib.auth.login(request, user)
#            return django.shortcuts.redirect('index')
#            #return True # TODO redirect (success)
#        else:
#            return False # TODO redirect (inactive user)
#    else:
#        return False # TODO redirect (invalid user)
    return django.shortcuts.redirect('index')

def logout(request):
    django.contrib.auth.logout(request)
    return django.shortcuts.redirect('index')

def edit(request, dataset):
    return ''

@require_POST
def add(request):
    # TODO: clean this up
    try:
        odp = request.POST['odp']
        description = request.POST['description']
        url_safe_name = re.sub('[ .!,;\-/\\\\]','_', odp.rsplit('/',1)[-1])
        try:
            dataset = Dataset.objects.get(name=url_safe_name)
            #logger.debug("Found db entry for {0}".format(url_safe_name))
            return django.shortcuts.redirect('index') # add "dataset exists"
        except:
            # TODO: generalize topology, spatial, temporal and layers into sciwms.util.meta
            # topology type
            topology_type = 'UNKNOWN'
            try:
                ug = pyugrid.UGrid.from_ncfile(odp, load_data=False)
                topology_type="UGRID"
            except:
                topology_type="CGRID"
            try:
                nc = netCDF4.Dataset(odp, 'r')
                # extents
                spatial_extent = meta.spatial_extent(nc)
                spatial_extent = [str(el) for el in spatial_extent]
                time_extent = meta.temporal_extent(nc)
                # layers
                layers = meta.get_layers(nc)
                attributes = {}
                attributes['spatial']   = spatial_extent
                attributes['temporal']  = time_extent
                attributes['url']       = odp+'.html'
                dataset = Dataset.objects.create(
                    name = url_safe_name,
                    description = description,
                    uri = odp,
                    json = json.dumps(attributes),
                    layers = layers,
                    topology_type = topology_type)
                logger.debug("Creating db entry for {0}".format(url_safe_name))
                dataset.save() 
                logger.debug("Updating Topology {0}".format(url_safe_name))
                update_dataset_cache(dataset) # TODO can we fork this?
                logger.debug("Done Updating Topology {0}".format(url_safe_name))
                return django.shortcuts.redirect('index')
            except:
                return django.shortcuts.redirect('index') # TODO: message about failure
                #return django.http.HttpResponseServerError("Unable to process the endpoint %s" % odp)
    except:
        # indicates the required POST fields were not given
        return django.shortcuts.redirect('index') # TODO: message about failure
        #return django.http.HttpResponseBadRequest()

def remove(request, dataset):
    d = Dataset.objects.get(name=dataset)
    d.delete()
    return django.shortcuts.redirect('index')

def refresh(request, dataset):
    return ''


def lower_request(request):
    gettemp = request.GET.copy()
    for key in request.GET.iterkeys():
        gettemp[key.lower()] = request.GET[key]
    request._set_get(gettemp)
    return request

def wms(request, dataset):
    try:

        # TODO: check dataset exists (return 204 otherwise)

        request = lower_request(request)

        r = request.GET.get('request', None)
        if r:
            if r.lower() == 'getmap':
                return getMap(request, dataset)
            elif r.lower() == 'getfeatureinfo':
                return getFeatureInfo(request, dataset)
            elif r.lower() == 'getlegendgraphic':
                return getLegendGraphic(request, dataset)
            elif r.lower() == 'getcapabilities':
                return getCapabilities(request, dataset)
        logger.info("dataset details for {0}".format(dataset))
        d = Dataset.objects.get(name=dataset)
        logger.info("d:".format(d))
        context = { 'dataset': d, 'sn': cf.standard_names } #TODO: dataset object
        #context = { 'dataset': d } #TODO: dataset object
        return django.shortcuts.render_to_response('wms/dataset.html', context, context_instance=RequestContext(request))

    except Exception:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        str_exc_descr = repr(traceback.format_exception(exc_type, exc_value, exc_traceback)) + '\n' + str(request)
        logger.error("Status 500 Error: " + str_exc_descr)
        return HttpResponse("<pre>Error: " + str_exc_descr + "</pre>", status=500)
