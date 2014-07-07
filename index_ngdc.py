import logging
import multiprocessing
import os
import re
import sys
import traceback
import time

from owslib import fes, csw
import netCDF4
import pyugrid
import json
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sciwms.settings.defaults")

from django.conf import settings

from sciwms.apps.wms.models import Dataset as dbDataset
from sciwms.libs.data.caching import update_dataset_cache
from sciwms.util import cf, meta

# TODO console logger
logger = logging.getLogger('')
logger.setLevel(logging.DEBUG)
format = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
ch = logging.StreamHandler(sys.stdout)
ch.setFormatter(format)
logger.addHandler(ch)


endpoint = "http://www.ngdc.noaa.gov/geoportal/csw"
uuid = '8BF00750-66C7-49FF-8894-4D4F96FD86C0'
uuid_filter = fes.PropertyIsEqualTo(propertyname='sys.siteuuid', literal="{{{0}}}".format(uuid))
timeout = 120

def main():

    # try twice
    reqcnt = 0
    while reqcnt < 2:
        try:
            logger.debug("Querying CSW Catalog {0} attempt {1}".format(endpoint, reqcnt+1))
            csw_catalogue = csw.CatalogueServiceWeb(endpoint, timeout = timeout)
            break
        except:
            #try one more time, timeouts sometimes occur
            logger.debug("Couldn't parse catalog on pass {0}, trying again in 30 seconds.".format(reqcnt))
            reqcnt += 1
            time.sleep(30)#give the server some extra time
    if reqcnt >= 2:
        logger.info("Couldn't Contact NGDC CSW Catalogue")
        raise ValueError("Couldn't Contact NGDC CSW Catalogue.")

    urls = {}
    update_topology=True
    nupdated = 0
    csw_catalogue.getrecords2([uuid_filter], esn='full', maxrecords=999999)
    for i, (name, record) in enumerate(csw_catalogue.records.iteritems()):

        # skipping 'preliminary' datasets
        if 'prelim' in name.lower():
            continue

        print name
        print record

        print "Processing {0} of {1}".format(i+1,len(csw_catalogue.records))
        url_safe_name = re.sub('[ .!,;\-/\\\\]','_', name)

        for ref in record.references:
            if 'odp' in ref.get('scheme').split(":"):
                uri = ref['url']

        # topology type
        topology_type = 'UNKNOWN'
        try:
            ug = pyugrid.UGrid.from_ncfile(uri, load_data=False)
            logger.info("Identified {0} as UGRID".format(url_safe_name))
            topology_type="UGRID"
        except:
            logger.info("Identified {0} as CGRID".format(url_safe_name))
            topology_type="CGRID"

        try:
            nc = netCDF4.Dataset(uri, 'r')

            # extents
            spatial_extent = meta.spatial_extent(nc)
            spatial_extent = [str(el) for el in spatial_extent]
            time_extent = meta.temporal_extent(nc)

            # layers
            layers = meta.get_layers(nc)

            logger.debug("{0}: {1}, {2}".format(url_safe_name, spatial_extent, time_extent))

            # ---------------------------------------------------
            # COMT specific attributes, placed in json blob in DB
            # ---------------------------------------------------
            attributes = {}

            # COMT event/storm
            storms = ['2004-2009','2005-2011','2004','IKE', 'RITA','2005', '2007', '2010', 'EXTRATROPICAL CYCLONES']
            storm = ""
            for strm in storms:
                if strm.lower() in uri.lower():
                    storm = strm
                    break

            # format of COMT catalog <host>/<category>/<org_model>/<dataset>
            split_url = uri.split("/")
            attributes['org_model'] = split_url[-2]
            attributes['category']  = split_url[-3]
            attributes['spatial']   = spatial_extent
            attributes['temporal']  = time_extent
            #attributes['layers']    = layers
            attributes['storm']     = storm
            attributes['url']       = uri+'.html'

            try:
                dataset = dbDataset.objects.get(name=url_safe_name)
                logger.debug("Found db entry for {0}".format(url_safe_name))
            except:
                dataset = dbDataset.objects.create(
                    name = url_safe_name,
                    description = name,
                    uri = uri,
                    json = json.dumps(attributes),
                    layers = layers,
                    topology_type = topology_type)
                logger.debug("Creating db entry for {0}".format(url_safe_name))
                dataset.save()
                logger.debug("Updating Topology {0}".format(url_safe_name))
                update_dataset_cache(dataset)
                logger.debug("Done Updating Topology {0}".format(url_safe_name))

        except:
            logger.error("Couldn't load {0} @ {1}".format(url_safe_name, uri))
            exc_type, exc_value, exc_traceback = sys.exc_info()
            logger.error("Disabling Error: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            nc = False


if __name__ == "__main__":
    main()
