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

import json
import numpy as np

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
    
def get_temporal_extent(nc):
    temp_ext = []
    
    tobj = nc.variables.get('time')
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
    layers = {}
    default_scalar_plot = "pcolor_average_jet_None_None_grid_False"
    default_vector_plot = "vectors_average_jet_None_None_grid_40"
    #MISC
    if 'u' and 'v' in nc.variables:
        layers['u,v'] = default_vector_plot

    if 'temp' in nc.variables:
        layers['temp'] = default_scalar_plot

    if 'zeta' in nc.variables:
        layers['zeta'] = default_scalar_plot

    if 'zeta_max' in nc.variables:
        layers['zeta_max'] = default_scalar_plot

    #SLOSH Variables
    if 'depth' in nc.variables:
        #IN BOTH SLOSH AND SELFE
        layers['depth'] = default_scalar_plot

    if 'etamax' in nc.variables:
        layers['etamax'] = default_scalar_plot    

    # if 'eta_max' in nc.variables:
    #     layers['eta_max'] = default_scalar_plot

    #ADCIRC Variables
    if 'zeta_max' in nc.variables:
        layers['zeta_max'] = default_scalar_plot

    if 'radstress_max' in nc.variables:
        layers['radstress_max'] = default_scalar_plot

    if 'vel_max' in nc.variables:
        layers['vel_max'] = default_scalar_plot

    if 'wind_max' in nc.variables:
        layers['wind_max'] = default_scalar_plot

    if 'swan_DIR_max' in nc.variables:
        layers['swan_DIR_max'] = default_scalar_plot

    if 'swan_TPS_max' in nc.variables:
        layers['swan_TPS_max'] = default_scalar_plot

    #FVCOM
    if 'maxele' in nc.variables:
        layers['maxele'] = default_scalar_plot

    if 'h' in nc.variables:
        layers['h'] = default_scalar_plot

    return layers
        
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
    print "Processing {0} of {1}".format(i+1,len(csw_catalogue.records))
    legal_name = re.sub('[ .!,;\-/\\\\]','_', name)

    for ref in record.references:
        if 'odp' in ref.get('scheme').split(":"):
            urls[legal_name] = ref['url']

    try:
        dataset = dbDataset.objects.get(name=legal_name)
        logger.debug("Found db entry for {0}".format(legal_name))
    except:
        dataset = dbDataset.objects.create(
            name=legal_name,
            title=name,
            abstract = "",
            keep_up_to_date=True,
            uri=urls[legal_name],
            display_all_timesteps = True)
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


        storms = ['IKE', 'RITA', '2005', '2007', '2010', 'EXTRATROPICAL CYCLONES']
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


    
        
    




