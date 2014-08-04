import glob
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

output_path = os.path.join(settings.PROJECT_ROOT, 'logs', 'sciwms_wms.log')
logger = multiprocessing.get_logger()
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(output_path)
formatter = logging.Formatter(fmt='[%(asctime)s] - <<%(levelname)s>> - |%(message)s|')
handler.setFormatter(formatter)
logger.addHandler(handler)

def remove_preliminary():
    for dataset in dbDataset.objects.all():
        if 'prelim' in dataset.name or 'preliminary' in dataset.name:
            logger.info("Removing {0} from db".format(dataset.name))
            
            cache_file_list = glob.glob(os.path.join(settings.TOPOLOGY_PATH,dataset.name + '*'))
            for cache_file in cache_file_list:
                logger.info("Removing {0} from topology cache".format(cache_file))
                os.remove(cache_file)
                
        


if __name__ == "__main__":
    remove_preliminary()
