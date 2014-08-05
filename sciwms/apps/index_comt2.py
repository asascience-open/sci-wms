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
from sciwms.util.cf import get_by_standard_name, get_global_attribute

from index_ngdc import get_temporal_extent, get_spatial_extent, get_layers

import json
import numpy as np

output_path = os.path.join(settings.PROJECT_ROOT, 'logs', 'sciwms_wms.log')
logger = multiprocessing.get_logger()
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(output_path)
formatter = logging.Formatter(fmt='[%(asctime)s] - <<%(levelname)s>> - |%(message)s|')
handler.setFormatter(formatter)
logger.addHandler(handler)

# from index_ngdc import get_temporal_extent, get_spatial_extent

default_scalar_plot = "pcolor_average_jet_None_None_grid_False"
default_vector_plot = "vectors_average_jet_None_None_grid_40"
""""
def get_spatial_extent(nc):
    bb = []
    try:
        lat = get_by_standard_name(nc, 'latitude')
        if not lat:
            raise Exception("lat is None")
        lon = get_by_standard_name(nc, 'longitude')
        if not lon:
            raise Exception("lon is None")
        lat = lat[:]
        lon = lon[:]
        bb = [np.nanmin(lon), np.nanmin(lat), np.nanmax(lon), np.nanmax(lat)]
    except:
        logger.info("Couldn't compute spatial extent")
        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error("Disabling Error: " +
                     repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    finally:
        return bb

def get_temporal_extent(nc):
    tobj = get_by_standard_name(nc, 'time')
    if not time:
        return []

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
        
    temp_ext = []
    if len(dates):
        temp_ext = [dates[0], dates[-1]]

    return temp_ext

"""
comt2 = {}
comt2['pr_inundation_tropical'] = {}
#UND ADCIRCSWAN
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_63_nc']={}
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_63_nc']['storm']='Hurricane Georges'
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_63_nc']['org_model']='UND_ADCIRCSWAN'
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_63_nc']['url'] = 'http://comt.sura.org/thredds/dodsC/comt_2_full/pr_inundation_tropical/UND_ADCIRCSWAN/Hurricane_Georges_2D_prelim_no_waves/Output/fort.63.nc'
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_63_nc']['layers'] = {'zeta':default_scalar_plot}
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_63_nc']['category']='pr_inundation_tropical'



comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_74_nc']={}
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_74_nc']['storm']='Hurricane Georges'
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_74_nc']['org_model']='UND_ADCIRCSWAN'
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_74_nc']['url'] = 'http://comt.sura.org/thredds/dodsC/comt_2_full/pr_inundation_tropical/UND_ADCIRCSWAN/Hurricane_Georges_2D_prelim_no_waves/Output/fort.74.nc'
# comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_74_nc']['variables']=['windx,windy']
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_74_nc']['layers']={'windx,windy':default_vector_plot}

comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_74_nc']['category']='pr_inundation_tropical'


#EMC ADCIRC-WW3
comt2['pr_inundation_tropical']['Dec2013Storm_2D_preliminary_run_1_waves_only'] = {}
comt2['pr_inundation_tropical']['Dec2013Storm_2D_preliminary_run_1_waves_only']['storm'] = 'Dec 2013 Storm'
comt2['pr_inundation_tropical']['Dec2013Storm_2D_preliminary_run_1_waves_only']['org_model']='EMC_ADCIRC_WW3'
comt2['pr_inundation_tropical']['Dec2013Storm_2D_preliminary_run_1_waves_only']['url'] = 'http://comt.sura.org/thredds/dodsC/comt_2_full/pr_inundation_tropical/EMC_ADCIRC-WW3/Dec2013Storm_2D_preliminary_run_1_waves_only/00_dir.ncml'
comt2['pr_inundation_tropical']['Dec2013Storm_2D_preliminary_run_1_waves_only']['layers'] =\
    {'u,v':default_vector_plot,'hs':default_scalar_plot,'wlv':default_scalar_plot,'U10,V10':default_vector_plot}
comt2['pr_inundation_tropical']['Dec2013Storm_2D_preliminary_run_1_waves_only']['category']='pr_inundation_tropical'

#NRL Delft3D
comt2['pr_inundation_tropical']['Hurricane_Ike_2D_preliminary_run_1_without_waves'] = {}
comt2['pr_inundation_tropical']['Hurricane_Ike_2D_preliminary_run_1_without_waves']['storm']='Hurricane Ike'
comt2['pr_inundation_tropical']['Hurricane_Ike_2D_preliminary_run_1_without_waves']['org_model']='NRL_Delft3D'
comt2['pr_inundation_tropical']['Hurricane_Ike_2D_preliminary_run_1_without_waves']['url'] = 'http://comt.sura.org/thredds/dodsC/comt_2_full/pr_inundation_tropical/NRL_Delft3D/Hurricane_Ike_2D_preliminary_run_1_without_waves/00_dir.ncml'
comt2['pr_inundation_tropical']['Hurricane_Ike_2D_preliminary_run_1_without_waves']['layers']=\
  {'waterlevel':default_scalar_plot,'velocity_x,velocity_y':default_vector_plot}
comt2['pr_inundation_tropical']['Hurricane_Ike_2D_preliminary_run_1_without_waves']['category']='pr_inundation_tropical'

def idx_comt2():
    update_topology=True
    pr_inundation = comt2['pr_inundation_tropical']

    for name in pr_inundation.keys():
        logger.info("Indexing {0}".format(name))
        js = {name:{}}

        nc = ncDataset(pr_inundation[name]['url'],'r')

        fbb = get_spatial_extent(nc,name)
        sbb = [str(el) for el in fbb]

        layers = get_layers(nc)
        js[name]['org_model'] = pr_inundation[name]['org_model']
        js[name]['category']  = pr_inundation[name]['category']
        js[name]['spatial']   = sbb
        js[name]['temporal']  = get_temporal_extent(nc)
        # js[name]['layers']    = pr_inundation[name]['layers']
        js[name]['layers']    = layers
        js[name]['storm']     = pr_inundation[name]['storm']
        js[name]['url']       = pr_inundation[name]['url']

        try:
            dataset = dbDataset.objects.get(name=name)
            logger.info("Found db entry for {0}".format(name))
        except:
            dataset = dbDataset(name=name,abstract='',title=name,keep_up_to_date=True,display_all_timesteps=True)
            logger.info("Created new db entry for {0}".format(name))

        dataset.uri = pr_inundation[name]['url']
        dataset.json = js
            
        dataset.save()
        if update_topology:
            logger.debug("Updating Topology {0}".format(dataset.name))
            update_dataset_cache(dataset)
            logger.debug("Done Updating Topology {0}".format(dataset.name))


    try:
        jsDataset = dbDataset.objects.get(name='json_all')
    except:
        jsDataset = dbDataset.objects.create(name='json_all',
                                             abstract='',
                                             title=name,
                                             keep_up_to_date=False,
                                             display_all_timesteps=False,
                                             json=[])

    jsall = []
    for dataset in dbDataset.objects.all():
        if dataset.name != "json_all":
            jsall.append(dataset.json)
    jsDataset.json=jsall
    jsDataset.save()

if __name__ == "__main__":
    idx_comt2()
