import logging
import multiprocessing
import os
import re
import sys
import traceback
import time

from owslib import fes, csw
import netCDF4
from netCDF4 import num2date, date2num

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sciwms.settings.defaults")

from django.conf import settings
from django.db.models import Q


from sciwms.apps.wms.models import Dataset as dbDataset
from sciwms.libs.data.caching import update_dataset_cache
from sciwms.util import cf
from sciwms.util.cf import long_names, get_by_standard_name, nc_name_from_standard, get_global_attribute
import json
import numpy as np

import pyugrid


from BeautifulSoup import BeautifulSoup
import urllib2
from urlparse import urlsplit, parse_qs
import re

def get_spatial_extent(nc, legal_name):

    lon = get_by_standard_name(nc, 'longitude')
    lat = get_by_standard_name(nc, 'latitude')

    if lon is not None and lat is not None:
        lon = lon[:]
        lat = lat[:]
        return [np.nanmin(lon), np.nanmin(lat), np.nanmax(lon), np.nanmax(lat)]

    try:
        if 'lat' and 'lon' in nc.variables:
            lon = nc.variables['lon'][:]
            lat = nc.variables['lat'][:]
        elif 'x' and 'y' in nc.variables:
            lon = nc.variables['x'][:]
            lat = nc.variables['y'][:]
        elif 'lat_u' and 'lon_u' in nc.variables:
            lon = nc.variables['lon_u'][:]
            lat = nc.variables['lat_u'][:]
        elif 'lat_v' and 'lon_v' in nc.variables:
            lon = nc.variables['lon_v'][:]
            lat = nc.variables['lat_v'][:]
        else:
            print "Couldn't Compute Spatial Extent {0}".format(legal_name)
            return []

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        print "Disabling Error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback))
        return []
    
    return [np.nanmin(lon), np.nanmin(lat), np.nanmax(lon), np.nanmax(lat)]
    
def get_temporal_extent(nc,time_var_name='time'):
    temp_ext = []
    
    # tobj = nc.variables.get(time_var_name)
    tobj = get_by_standard_name(nc, 'time')
    if tobj:
        tkwargs = {}
        if hasattr(tobj, 'units'):
            tkwargs['units'] = tobj.units
        if hasattr(tobj, 'calendar'):
            tkwargs['calendar'] = tobj.calendar.lower()

        times = tobj[:]
        dates = []
        for t in times:
            try:
                dates.append(num2date(t, **tkwargs))
            except:
                pass

        if len(dates):
            temp_ext = [dates[0], dates[-1]]

    return temp_ext

def get_layers(nc):

    # return dict: key is UI displayable name (eg. shown in badges), value is default style for this layer
    layers = {}

    # disabling auto-scaling by requireing min/max values
    #default_scalar_plot = "pcolor_average_jet_%s_%s_grid_False"
    #default_vector_plot = "vectors_average_jet_%s_%s_grid_40"
    default_scalar_plot = "pcolor_average_jet_%.1f_%.1f_grid_False"
    default_vector_plot = "vectors_average_jet_%.1f_%.1f_grid_40"
    
    ##id = get_global_attribute(nc,'id')
    ##model = get_global_attribute(nc,'model')
    #id = getattr(nc, 'id', None)
    #model = getattr(nc, 'model', None)
    #print '\t\tNetCDF global attribute [id] = {0}'.format(id)
    #print '\t\tNetCDF global attribute [model] = {0}'.format(model)

    # NetCDF variables, if standard_name exists and is in util/cf default_scales, add, else, we ignore
    for vn, v in nc.variables.iteritems():
        sn = getattr(v, 'standard_name', None)
        # if no standard_name, try known long_name
        if sn is None:
            ln = getattr(v, 'long_name', None)
            if ln is None:
                continue # if no long_name, just quit trying
            for s,l in long_names.iteritems():
                if ln == l:
                    sn = s
        if sn is None:
            continue
        sn = sn.lower()
        #print 'NetCDF variable name = {0}, CF standard_name = {1}'.format(vn, sn)
        if sn in cf.default_scales.keys():
            min, max = cf.default_scales.get(sn, None)
            style = default_scalar_plot % (min, max)
            print '\t\tadding %s (NetCDF var) with LAYER name (CF standard_name) %s and default STYLE %s' % (vn, sn, style)
            layers[sn] = style


    # -------------------
    # VECTOR HACK SECTION
    # -------------------
    # adds vector field 'u,v' to LAYERS and removes u and v from LAYERS
    # TODO: this is a hack, whats a good way to do this?
    if 'eastward_sea_water_velocity' in layers and 'northward_sea_water_velocity' in layers:
        layers['eastward_sea_water_velocity,northward_sea_water_velocity'] = 'vectors_average_jet_0.0_2.0_grid_40' #TODO use scale_min/scale_max
        del layers['eastward_sea_water_velocity']
        del layers['northward_sea_water_velocity']
    if 'eastward_wind' in layers and 'northward_wind' in layers:
        layers['eastward_wind,northward_wind'] = 'vectors_average_jet_0_50_grid_40' #TODO use scale_min/scale_max
        del layers['eastward_wind']
        del layers['northward_wind']
    if 'barotropic_eastward_sea_water_velocity' in layers and 'barotropic_northward_sea_water_velocity' in layers:
        layers['barotropic_eastward_sea_water_velocity,barotropic_northward_sea_water_velocity'] = 'vectors_average_jet_0.0_2.0_grid_40' #TODO: use scale_min/scale_max
        del layers['barotropic_eastward_sea_water_velocity']
        del layers['barotropic_northward_sea_water_velocity']

    # no time, latitude, longitude passed back TODO: hack
    layers.pop('time', None)
    layers.pop('latitude', None)
    layers.pop('longitude', None)

    return layers

def main():

    json_all = []
    update_topology=True
    nupdated = 0

    # COMT 1 Archive Summary URL
    comt = urllib2.urlopen('http://comt.sura.org/thredds/comt_1_archive_summary.html')
    # find all <a> links to COMT data
    soup = BeautifulSoup(comt)
    a_tags = soup.findAll('a')

    odp_id = []
    for link in a_tags:
        href = link.get('href', '')
        if href.startswith('comt_1_archive_summary.html'):
            url = urlsplit(href)
            query = parse_qs(url.query)

            id = query['dataset'][0]
            name = id

            # skip records indicating they are PRELIMINARY simulations (TODO: should not be submitted to NGDC?)
            if 'prelim' in name.lower() or 'testing' in name.lower():
                continue

            category, org_model, run = id.split('.')

            # build the OpenDAP URL
            odp = 'http://comt.sura.org/thredds/dodsC/data/comt_1_archive/{0}/{1}/{2}'.format(category, org_model, run)

            odp_id.append((odp,id))

    odp_id = []

    # MANUAL COMT2 additions
    odp_id.append(('http://oceanmodeling.pmc.ucsc.edu:8080/thredds/dodsC/ccsnrt_physbio/fmrc/CCSNRT_Phys_Bio_Aggregation_best.ncd','usw_integration.ccsnrt_physbio.fmrc'))
    odp_id.append(('http://comt.sura.org/thredds/dodsC/comt_2_full/pr_inundation_tropical/UND_ADCIRCSWAN/Hurricane_Georges_2D_prelim_no_waves/Output/fort.63.nc','pr_inundation_tropical.UND_ADCIRCSWAN.Hurricane_Georges_2D_prelim_no_waves'))
    odp_id.append(('http://comt.sura.org/thredds/dodsC/comt_2_full/pr_inundation_tropical/EMC_ADCIRC-WW3/Dec2013Storm_2D_preliminary_run_1_waves_only/00_dir.ncml','pr_inundation_tropical.EMC_ADCIRC-WW3.Dec2013Storm_2D_preliminary_run_1_waves_only'))
    odp_id.append(('http://comt.sura.org/thredds/dodsC/comt_2_full/pr_inundation_tropical/NRL_Delft3D/Hurricane_Ike_2D_preliminary_run_1_without_waves/00_dir.ncml','pr_inundation_tropical.NRL_Delft3D.Hurricane_Ike_2D_preliminary_run_1_without_waves'))

    for odp,id in odp_id:

            name = id

            category, org_model, run = id.split('.')

            print ""

            legal_name = re.sub('[ .!,;\-/\\\\]','_', name) # TODO: what is legal about legal_name?

            # build the OpenDAP URL
            url = odp + '.html'

#            print name, category, org_model, run
#            print odp
#            print url

#            continue


            # check if entry already exists in DB, if not, set one up
            try:
                dataset = dbDataset.objects.get(name=legal_name)
                print "Found db entry for {0}".format(legal_name)
            except:
                dataset = dbDataset.objects.create(
                    name=legal_name,
                    title=name,
                    abstract = "",
                    keep_up_to_date=True,
                    uri=odp,
                    display_all_timesteps = True)
                print "Creating db entry for {0}".format(legal_name)


            # get NetCDF object (TODO: only bother if it's a valid NetCDF file, right?)
            try:
                nc = netCDF4.Dataset(odp, 'r')
            except:
                print "Couldn't load {0} @ {1}".format(legal_name, odp)
                exc_type, exc_value, exc_traceback = sys.exc_info()
                print "Disabling Error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback))
                nc = False
                continue


            # determine topology type

            topology_type=""
            try:
                ug = pyugrid.UGrid.from_nc_dataset(nc, load_data=False)
                print "\t\tUGRID"
                topology_type="ugrid"
            except:
                print "\t\tCGRID"
                topology_type="cgrid"

            dataset.topology_type = topology_type


            if nc:

                id = getattr(nc, 'id', id)
                model = getattr(nc, 'model', None)
                print '\t\tNetCDF global attribute [id] = {0}'.format(id)
                print '\t\tNetCDF global attribute [model] = {0}'.format(model)

                category, org_model, run = id.split('.')
                print '\t\t\tCOMT Testbed attribute (from id) [category] = {0}'.format(category)
                print '\t\t\tCOMT Testbed attribute (from id) [org_model] = {0}'.format(org_model)
                print '\t\t\tCOMT Testbed attribute (from id) [run] = {0}'.format(run)

                # NetCDF file dimensions
                spatial_ext = get_spatial_extent(nc, legal_name)
                spatial_ext = [str(el) for el in spatial_ext]
                time_ext = get_temporal_extent(nc)

                # gets CF standard_name variables for WMS LAYERS, will only add if a scale is also defined in util/cf
                layers = get_layers(nc)

                print "\t\t{0}: {1}, {2}".format(legal_name, spatial_ext, time_ext)

                ####################
                # TESTBED SPECIFIC #
                ####################

                #2004 is for esturine hypoxia
                storms = ['2004-2009','2005-2011','2004','IKE', 'RITA','2005', '2007', '2010', 'EXTRATROPICAL CYCLONES']
                storm = "NA"
                for strm in storms:
                    if strm.lower() in odp.lower():
                        storm = strm
                        break

                js = {legal_name:{}}
                js[legal_name]['org_model'] = org_model
                js[legal_name]['category']  = category
                js[legal_name]['spatial']   = spatial_ext
                js[legal_name]['temporal']  = time_ext
                js[legal_name]['layers']    = layers
                js[legal_name]['storm']     = storm
                js[legal_name]['url']       = url

                # default_layer is empty, this is only for the test page
                js[legal_name]['default_layer'] = ""

                print '\t\t{0}'.format(js)
                print ''

                dataset.json = js

                dataset.save()

                json_all.append(js)

                if update_topology:
                    print "Updating Topology {0}".format(legal_name)
                    update_dataset_cache(dataset)
                    nupdated += 1
                    print "Done Updating Topology {0}".format(legal_name)

########################################
# JSON_ALL - TODO: replace this method #
########################################

    try:
        dataset = dbDataset.objects.get(name="json_all")
        print "Found Existing json_all entry"
    except:
        dataset = dbDataset.objects.create(
            name="json_all",
            title="",
            uri="",
            abstract="",
            keep_up_to_date=False,
            display_all_timesteps=False)

    dataset.json = json_all
    dataset.save()

if __name__ == "__main__":
    main()
