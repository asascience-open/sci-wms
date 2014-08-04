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


def remove_preliminary():
    
    for dataset in dbDataset.objects.all():
        print dataset.name
        if 'prelim' in dataset.name or 'preliminary' in dataset.name:
            print "\t{0}".format(dataset.name)


if __name__ == "__main__":
    remove_preliminary()
