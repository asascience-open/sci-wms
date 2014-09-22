import multiprocessing
import logging
import os
import re
import sys
import traceback
import time
import json

from owslib import fes, csw
from netCDF4 import Dataset as ncDataset
from netCDF4 import num2date, date2num

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sciwms.settings.defaults")

from sciwms.apps.wms.models import Dataset as dbDataset
from sciwms.libs.data.caching import update_dataset_cache
from sciwms.util import cf
from sciwms.util.cf import get_by_standard_name, nc_name_from_standard, get_global_attribute
import json
import numpy as np

logger = multiprocessing.get_logger()
logger.setLevel(logging.DEBUG)

alias_to_std = {
   'time': {'standard_name':'time'},
   'longitude': {'standard_name':'longitude', 'scale_min':'0', 'scale_max':'360'},
   'latitude': {'standard_name':'latitude', 'scale_min':'-90', 'scale_max':'90'},
   'ssh_geoid': {'standard_name':'sea_surface_height_above_geoid', 'scale_min':'0', 'scale_max':'7.0'},
   'ssh_reference_datum': {'standard_name':'water_surface_height_above_reference_datum', 'scale_min':'0', 'scale_max':'7.0'},
   'u': {'standard_name':'eastward_sea_water_velocity', 'scale_min':'0', 'scale_max':'2'},
   'v': {'standard_name':'northward_sea_water_velocity', 'scale_min':'0', 'scale_max':'2'},
   'hs': {'standard_name':'sea_surface_wave_significant_height', 'scale_min':'0', 'scale_max':'12'},
   'uwind': {'standard_name':'eastward_wind', 'scale_min':'0', 'scale_max':'80'},
   'vwind': {'standard_name':'northward_wind', 'scale_min':'0', 'scale_max':'80'},
   'salinity': {'standard_name':'sea_water_salinity', 'scale_min':'32', 'scale_max':'37'},
   'sst': {'standard_name':'sea_water_temperature', 'scale_min':'0', 'scale_max':'40'},
   'ubarotropic': {'standard_name':'barotropic_eastward_sea_water_velocity', 'scale_min':'0', 'scale_max':'2'},
   'vbarotropic': {'standard_name':'barotropic_northward_sea_water_velocity', 'scale_min':'0', 'scale_max':'2'},
}

json_all = []
for dataset in dbDataset.objects.all():
    print dataset.name


    if dataset.name != 'json_all':
        js = dataset.json

        if js:

            print "--------------------------------------------"
            layers = js[dataset.name].get('layers')
            print "layers = {0}".format(layers)
            if layers:
                print "$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$"
                print "old js layers = {0}".format(js[dataset.name]['layers'])
                
                new_layers = {}
                for old_key in js[dataset.name]['layers'].keys():
                    print js[dataset.name]['layers'][old_key]
                    klist = old_key.split(",")
                    new_key_list = []
                    for kel in klist:
                        if kel in alias_to_std.keys():
                            new_key_list.append(alias_to_std.get(kel).get('standard_name'))
                        else:
                            new_key_list.append(kel)

                    new_key = ",".join(new_key_list)

                    print ""
                    print "old_key: {0} -> new_key: {1}".format(old_key, new_key)
                    print "old layer: {0}".format(js[dataset.name]['layers'][old_key])
                    print ""
                    new_layers[new_key] = js[dataset.name]['layers'][old_key]

                js[dataset.name]['layers'] = new_layers
                print "new js layers = {0}".format(js)
                
            # default_layer = js[dataset.name].get('default_layer')
            # if default_layer:
            #     print "*******************************************************"
            #     print "old_default = {0}".format(default_layer)
            #     for old_key in js[dataset.name]['default_layer'].keys():
            #         klist = old_key.split(",")

            #         new_key
            #         if len(klist) == 1:
            #             if klist[0] in alias_to_std.keys():
            #                 pass

        json_all.append(js)
        dataset.json = js
        dataset.save()


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
