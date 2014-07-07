import json
import logging
import os
import re
import sys
import time
import netCDF4
from netCDF4 import num2date, date2num

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sciwms.settings.defaults")

from django.conf import settings
from django.db.models import Q


from sciwms.apps.wms.models import Dataset as dbDataset
from sciwms.libs.data.caching import update_dataset_cache
from sciwms.util import cf, meta
from sciwms.util.cf import long_names, get_by_standard_name
import json
import numpy as np

import pyugrid

import re

# -------------------------
from lxml import etree
# CF conventions (standard_names)
cf_standard_name_table = 'cf-standard-name-table.xml'
doc = etree.parse(cf_standard_name_table)
version = doc.find('version_number')
standard_names = []
entries = doc.findall('//entry')
for entry in entries:
    if 'id' in entry.attrib:
        standard_names.append(entry.get('id'))
# -------------------------


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

    # return dict: key is NetCDF variable name, value is standard_name, empty if no-standard name (so user can supply it)
    layers = {}

    # NetCDF variables, if standard_name exists and is in util/cf default_scales, add, else, we ignore
    for vn, v in nc.variables.iteritems():
        # skip variables with a single dimension (not plottable)
        if v.ndim == 1:
            continue
        sn = getattr(v, 'standard_name', None)
        ln = getattr(v, 'long_name', None)
        units = getattr(v, 'units', None)
#        # if no standard_name, try known long_name
#        if sn is None:
#            ln = getattr(v, 'long_name', None)
#            if ln is None:
#                continue # if no long_name, just quit trying
#            for s,l in long_names.iteritems():
#                if ln == l:
#                    sn = s
#        if sn is None:
#            continue
        if sn:
            sn = sn.lower()
        if sn not in standard_names:
            print "unknown standard_name {0}".format(sn)
            sn = None
        #print 'NetCDF variable name = {0}, CF standard_name = {1}'.format(vn, sn)
#        if sn in cf.default_scales.keys():
#            min, max = cf.default_scales.get(sn, None)
#            style = default_scalar_plot % (min, max)
        # TODO: look up default range for standard_name and units
        print '\t\tadding %s (NetCDF var) with LAYER name (CF standard_name) %s' % (vn, sn)
        layers[vn] = {'standard_name': sn, 'long_name': ln, 'units': units}

#    # no time, latitude, longitude passed back TODO: hack
#    layers.pop('time', None)
#    layers.pop('latitude', None)
#    layers.pop('longitude', None)

    return layers

def main():

    # OPeNDAP endpoint, name, description, arbitrary JSON/dict
    odp_id = []
    odp_id.append(('http://reanalysis.asa.rocks/thredds/dodsC/ERA-Interim-MET','ERA-Interim-MET','ERA-Interim global atmospheric reanalysis','{}'))
    odp_id.append(('http://reanalysis.asa.rocks/thredds/dodsC/ERA-Interim-WAVE','ERA-Interim-WAVE','ERA-Interim global wave reanalysis','{}'))
    odp_id.append(('http://reanalysis.asa.rocks/thredds/dodsC/WW3-CFSRR','WW3-CFSRR','WAVEWATCH III CFSR Reanalysis Hindcasts','{}'))
    odp_id.append(('http://comt.sura.org/thredds/dodsC/comt_1_archive_full/inundation_extratropical/UMASS_FVCOM/2005_3D_final_run_without_waves/00_dir.ncml','COMT-UMASS-FVCOM-2005','COMT - Extratropical Inundation - UMASS FVCOM - 2005 3D final without waves','{"category": "inundation_extratropical", "storm": "2005", "org_model": "UMASS_FVCOM"}'))


    for odp,id,description,attributes in odp_id:
        name = id

        legal_name = re.sub('[ .!,;\-/\\\\]','_', name) # URL safe name

        # build the OpenDAP URL
        url = odp + '.html'

        # check if entry already exists in DB, if not, set one up
        try:
            dataset = dbDataset.objects.get(name=legal_name)
            print "Found db entry for {0}".format(legal_name)
        except:
            dataset = dbDataset.objects.create(
                name=legal_name,
                description = description,
                uri=odp,
                json=attributes)
            print "Creating db entry for {0}".format(legal_name)

         # get NetCDF object (TODO: only bother if it's a valid NetCDF file, right?)
        try:
            nc = netCDF4.Dataset(odp, 'r')
        except:
            continue


        # determine topology type
        topology_type=""
        try:
            ug = pyugrid.UGrid.from_nc_dataset(nc, load_data=False)
            print "\t\tUGRID"
            topology_type="UGRID"
        except:
            print "\t\tCGRID"
            topology_type="CGRID"
        dataset.topology_type = topology_type

        if nc:

            # NetCDF file dimensions
            spatial_ext = get_spatial_extent(nc, legal_name)
            spatial_ext = [str(el) for el in spatial_ext]
            time_ext = get_temporal_extent(nc)

            # gets CF standard_name variables for WMS LAYERS, will only add if a scale is also defined in util/cf
            layers = meta.get_layers(nc)
            print json.dumps(layers)

            print "\t\t{0}: {1}, {2}".format(legal_name, spatial_ext, time_ext)

            dataset.layers = layers

            dataset.save()

            print "Updating Topology {0}".format(legal_name)
            update_dataset_cache(dataset)
            print "Done Updating Topology {0}".format(legal_name)

if __name__ == "__main__":
    main()
