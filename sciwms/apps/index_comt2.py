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

from index_ngdc import get_temporal_extent, get_spatial_extent
comt2 = {}
comt2['pr_inundation_tropical'] = {}
#UND ADCIRCSWAN
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_63_nc']={}
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_63_nc']['storm']='Hurricane Georges'
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_63_nc']['org_model']='UND_ADCIRCSWAN'
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_63_nc']['url'] = 'http://comt.sura.org/thredds/dodsC/comt_2_full/pr_inundation_tropical/UND_ADCIRCSWAN/Hurricane_Georges_2D_prelim_no_waves/Output/fort.63.nc'
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_63_nc']['variables'] = ['zeta']

comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_74_nc']={}
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_74_nc']['storm']='Hurricane Georges'
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_74_nc']['org_model']='UND_ADCIRCSWAN'
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_74_nc']['url'] = 'http://comt.sura.org/thredds/dodsC/comt_2_full/pr_inundation_tropical/UND_ADCIRCSWAN/Hurricane_Georges_2D_prelim_no_waves/Output/fort.74.nc'
comt2['pr_inundation_tropical']['Hurricane_Georges_2D_prelim_no_waves_fort_74_nc']['variables']=['windx,windy']

#EMC ADCIRC-WW3
comt2['pr_inundation_tropical']['Dec2013Storm_2D_preliminary_run_1_waves_only'] = {}
comt2['pr_inundation_tropical']['Dec2013Storm_2D_preliminary_run_1_waves_only']['storm'] = 'Dec 2013 Storm'
comt2['pr_inundation_tropical']['Dec2013Storm_2D_preliminary_run_1_waves_only']['org_model']='EMC_ADCIRC_WW3'
comt2['pr_inundation_tropical']['Dec2013Storm_2D_preliminary_run_1_waves_only']['url'] = 'http://comt.sura.org/thredds/dodsC/comt_2_full/pr_inundation_tropical/EMC_ADCIRC-WW3/Dec2013Storm_2D_preliminary_run_1_waves_only/00_dir.ncml'
comt2['pr_inundation_tropical']['Dec2013Storm_2D_preliminary_run_1_waves_only']['variables']=['u,v','hs','wlv','U10,V10']

#NRL Delft3D
comt2['pr_inundation_tropical']['Hurricane_Ike_2D_preliminary_run_1_without_waves'] = {}
comt2['pr_inundation_tropical']['Hurricane_Ike_2D_preliminary_run_1_without_waves']['storm']='Hurricane Ike'
comt2['pr_inundation_tropical']['Hurricane_Ike_2D_preliminary_run_1_without_waves']['org_model']='NRL_Delft3D'
comt2['pr_inundation_tropical']['Hurricane_Ike_2D_preliminary_run_1_without_waves']['url'] = 'http://comt.sura.org/thredds/dodsC/comt_2_full/pr_inundation_tropical/NRL_Delft3D/Hurricane_Ike_2D_preliminary_run_1_without_waves/00_dir.ncml'
comt2['pr_inundation_tropical']['Hurricane_Ike_2D_preliminary_run_1_without_waves']['variables']=['waterlevel','velocity_x,velocity_y']


if __name__ == "__main__":
    for name in comt2['pr_inundation_tropical'].keys():
        print name
        for k in comt2['pr_inundation_tropical'][name].keys():
            print "\t{0}:{1}".format(k,comt2['pr_inundation_tropical'][name][k])
        # print comt2['pr_inundation_tropical'][name]['url']
        # print comt2['pr_inundation_tropical'][name]['variables']

        # json = {name:}
    


        # json = {}
        # dataset, created_bool =\
        #     dbDataset.objects,get_or_create(name='Hurricane_Ike_2D_preliminary_run_1_without_waves_for_63_nc',
        #                                     abstract='',
        #                                     title='Hurricane_Ike_2D_preliminary_run_1_without_waves_for_63_nc',
        #                                     url='http://comt.sura.org/thredds/dodsC/comt_2_full/'
        #                                     'pr_inundation_tropical/UND_ADCIRCSWAN/'
        #                                     'Hurricane_Georges_2D_prelim_no_waves/Output/fort.63.nc',
        #                                     keep_up_to_date=True,
        #                                     display_all_timesteps=True)

