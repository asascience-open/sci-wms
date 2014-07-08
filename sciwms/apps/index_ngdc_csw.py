#this is ~/index_ngdc_csw.py
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sciwms.settings.defaults")
from sciwms.apps.index_csw import index_csw

from django.conf import settings

# if __name__ == "__main__":
#NGDCGeoportal
endpoint = 'http://www.ngdc.noaa.gov/geoportal/csw'

#testbed uuid
constraints = [('sys.siteuuid', '8BF00750-66C7-49FF-8894-4D4F96FD86C0')]

index_csw(endpoint, constraints, insert_djangodb = True, update_topology=True)



