import logging
import multiprocessing
import os
import re
import sys
import traceback
import time

from owslib import fes, csw
from netCDF4 import Dataset as ncDataset
from netCDF4 import num2date, date2num

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sciwms.settings.defaults")

from django.conf import settings
from django.db.models import Q


from sciwms.apps.wms.models import Dataset as dbDataset
from sciwms.libs.data.caching import update_dataset_cache
from sciwms.util import cf
from sciwms.util.cf import get_by_standard_name, nc_name_from_standard, get_global_attribute
import json
import numpy as np

import pyugrid

output_path = os.path.join(settings.PROJECT_ROOT, 'logs', 'sciwms_wms.log')
logger = multiprocessing.get_logger()
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(output_path)
formatter = logging.Formatter(fmt='[%(asctime)s] - <<%(levelname)s>> - |%(message)s|')
handler.setFormatter(formatter)
logger.addHandler(handler)

endpoint = "http://www.ngdc.noaa.gov/geoportal/csw"
uuid = '8BF00750-66C7-49FF-8894-4D4F96FD86C0'
uuid_filter = fes.PropertyIsEqualTo(propertyname='sys.siteuuid', literal="{{{0}}}".format(uuid))
timeout = 120

def get_spatial_extent(nc, legal_name):
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
            logger.info("Couldn't Compute Spatial Extent {0}".format(legal_name))
            return []

    except:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error("Disabling Error: " +
                     repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
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

def get_layers(nc, vars=['depth','u,v']):

    '''
    BM: updating 20140801 to use UI names defined in sciwms/util/cf
        only variables with CF compliant standard_name can be added
    '''

    # return dict: key is UI displayable name (eg. shown in badges), value is default style for this layer
    layers = {}

    # disabling auto-scaling by requireing min/max values
    default_scalar_plot = "pcolor_average_jet_%s_%s_grid_False"
    default_vector_plot = "vectors_average_jet_%s_%s_grid_40"
    
    nc_id = get_global_attribute(nc,'id')
    nc_model = get_global_attribute(nc,'model')
    print 'nc_id = {0}'.format(nc_id)
    print 'nc_model = {0}'.format(nc_model)

    # going to loop through the variables in NetCDF object, if standard_name exists and is in util/cf map, add, else, ignore
    for variable_name, variable in nc.variables.iteritems():
        # standard_name
        standard_name = nc.variables[variable_name].__dict__.get('standard_name', None)
        if standard_name == None:
            continue
        print 'variable name = {0}, standard name = {1}'.format(variable_name, standard_name)
        # cell_methods (standard_name is not always unique in Dataset)
        cell_methods = nc.variables[variable_name].__dict__.get('cell_methods', None)
        # if cell_method specified, prepend cell_method to standard_name for uniqueness
        if cell_methods != None:
            cell_methods = re.sub(":\s+", "_", cell_methods)
            cell_methods = re.sub("\s+", "", cell_methods)
            standard_name = '%s_%s' % (cell_methods, standard_name)
        # is this standard_name in the cf.map?
        for k,v in cf.map.items():
            # if standard_name is in map, add to layers dict with style as value
            if v['standard_name'] == standard_name:
                scale_min = v.get('scale_min', None)
                scale_max = v.get('scale_max', None)
                style = default_scalar_plot % (scale_min, scale_max)
                logger.info('adding %s with LAYER name %s and default STYLE %s' % (standard_name, k, style))
                print 'adding %s with LAYER name %s and default STYLE %s' % (standard_name, k, style)
                layers[k] = style

    # ---------------------------
    # HACK SECTION
    # ---------------------------
    # if combine vector fields TODO: hack, whats a good way to do this?
    if 'u' in layers and 'v' in layers:
        layers['u,v'] = 'vectors_average_jet_0_2_grid_40' #TODO use scale_min/scale_max
        del layers['u']
        del layers['v']
    if 'uwind' in layers and 'vwind' in layers:
        layers['uwind,vwind'] = 'vectors_average_jet_0_50_grid_40' #TODO use scale_min/scale_max
        del layers['uwind']
        del layers['vwind']
    if 'ubarotropic' in layers and 'vbarotropic' in layers:
        layers['ubarotropic,vbarotropic'] = 'vectors_average_jet_0_2_grid_40' #TODO use scale_min/scale_max
        del layers['ubarotropic']
        del layers['vbarotropic']

    # no time, latitude, longitude passed back TODO: hack
    layers.pop('time', None)
    layers.pop('latitude', None)
    layers.pop('longitude', None)

    print layers.keys()

    return layers

def main():
    reqcnt = 0
    while reqcnt < 2:
        try:
            logger.debug("Querying CSW Catalog {0} attempt {1}".format(endpoint, reqcnt+1))
            csw_catalogue = csw.CatalogueServiceWeb(endpoint, timeout = timeout)
            break
        except:
            #try one more time, timeouts sometimes occur
            logger.debug("Couldn't parse catalog on pass {0}, trying again in 30 seconds.".format(reqcnt))
            exc_type, exc_value, exc_traceback = sys.exc_info()
            str_exc_descr = repr(traceback.format_exception(exc_type, exc_value, exc_traceback))
            logger.info(str_exc_descr)
            reqcnt += 1
            time.sleep(30)#give the server some extra time

    if reqcnt >= 2:
        logger.info("Couldn't Contact NGDC CSW Catalogue")
        raise ValueError("Couldn't Contact NGDC CSW Catalogue.")


    urls = {}
    json_all = []
    update_topology=True
    nupdated = 0
    csw_catalogue.getrecords2([uuid_filter], esn='full', maxrecords=999999)
    for i, (name, record) in enumerate(csw_catalogue.records.iteritems()):
        if 'prelim' in name or 'preliminary' in name:
            continue
        
        print "Processing {0} of {1}".format(i+1,len(csw_catalogue.records))
        legal_name = re.sub('[ .!,;\-/\\\\]','_', name)

        for ref in record.references:
            if 'odp' in ref.get('scheme').split(":"):
                urls[legal_name] = ref['url']

        try:
            dataset = dbDataset.objects.get(name=legal_name)
            logger.debug("Found db entry for {0}".format(legal_name))
        except:
            topology_type=""
            try:
                
                ug = pyugrid.UGrid.from_ncfile(urls[legal_name], load_data=False)
                logger.info("Identified {0} as ugrid".format(legal_name))
                topology_type="ugrid"
            except:
                logger.info("Identified {0} as cgrid".format(legal_name))
                topology_type="cgrid"
                
            dataset = dbDataset.objects.create(
                name=legal_name,
                title=name,
                abstract = "",
                keep_up_to_date=True,
                uri=urls[legal_name],
                display_all_timesteps = True,
                topology_type=topology_type)
            logger.debug("Creating db entry for {0}".format(legal_name))

        try:
            nc = ncDataset(urls[legal_name],'r')
        except:
            logger.error("Couldn't load {0} @ {1}".format(legal_name, urls[legal_name]))
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.error("Disabling Error: " +
                         repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            nc = False

        if nc:
            spatial_ext = get_spatial_extent(nc, legal_name)
            spatial_ext = [str(el) for el in spatial_ext]
            time_ext = get_temporal_extent(nc)
            layers = get_layers(nc)


            # if len(time_ext):
            #     tlist = ["{0}".format(time_ext[0]), "{0}".format(time_ext[1])]

            logger.debug("{0}: {1}, {2}".format(legal_name, spatial_ext, time_ext))


            #2004 is for esturine hypoxia
            storms = ['2004-2009','2005-2011','2004','IKE', 'RITA','2005', '2007', '2010', 'EXTRATROPICAL CYCLONES']
            storm = ""
            for strm in storms:
                if strm.lower() in urls[legal_name].lower():
                    storm = strm
                    break

            split_url = urls[legal_name].split("/")
            js = {legal_name:{}}
            js[legal_name]['org_model'] = split_url[-2]
            js[legal_name]['category']  = split_url[-3]
            js[legal_name]['spatial']   = spatial_ext
            js[legal_name]['temporal']  = time_ext
            js[legal_name]['layers']    = layers
            js[legal_name]['storm']     = storm
            js[legal_name]['url']       = urls[legal_name]

            #default layer for plotting in web-portal
            org_model = js[legal_name]['org_model']
            default_layer = ''
            if org_model.lower() == 'umass_fvcom':
                default_layer = 'zeta'

            elif org_model.lower() == 'usf_fcvom':
                default_layer = 'maxele'

            elif org_model.lower() == 'mdl_slosh':
                default_layer = 'etamax'

            elif org_model.lower() == 'und_adcirc':
                default_layer = 'zeta_max'
                if not 'zeta_max' in nc.variables:
                    if 'zeta' in nc.variables:
                        default_layer = 'zeta'

            elif org_model.lower() == 'ums_selfe':
                default_layer = 'elev'

            elif org_model.lower() == 'dal_roms':
                default_layer = 'temp'

            elif org_model.lower() == 'tamu_roms':
                default_layer = 'temp'

            #hard-coded fringe datasets
            elif legal_name.lower() == "shelf_hypoxia_NOAA_NGOM_2005_2011_NGOM".lower():
                default_layer = 'temp'

            elif legal_name.lower() == "estuarine_hypoxia_VIMS_CBOFS_2004_2005".lower():
                default_layer = 'temp'

            if default_layer in js[legal_name]['layers']:
                js[legal_name]['default_layer'] = default_layer
            else:
                js[legal_name]['default_layer'] = ""

            dataset.json = js

            dataset.save()

            json_all.append(js)

            if update_topology:
                logger.debug("Updating Topology {0}".format(legal_name))
                update_dataset_cache(dataset)
                nupdated += 1
                logger.debug("Done Updating Topology {0}".format(legal_name))

    try:
        dataset = dbDataset.objects.get(name="json_all")
        logger.debug("Found Existing json_all entry")
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
