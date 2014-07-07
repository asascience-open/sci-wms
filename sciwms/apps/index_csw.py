import logging
import multiprocessing
import os
import re
import sys
import traceback

from owslib import fes, csw
from netCDF4 import Dataset as ncDataset

from django.conf import settings
from django.db.models import Q

from sciwms.apps.wms.models import Dataset as sciwmsDataset
from sciwms.libs.data.caching import update_dataset_cache

import json

output_path = os.path.join(settings.PROJECT_ROOT, 'logs', 'sciwms_wms.log')
logger = multiprocessing.get_logger()
logger.setLevel(logging.INFO)
handler = logging.FileHandler(output_path)
formatter = logging.Formatter(fmt='[%(asctime)s] - <<%(levelname)s>> - |%(message)s|')
handler.setFormatter(formatter)
logger.addHandler(handler)

def json_helper(name, uri):
    storms = ['IKE', 'RITA', '2005', '2007', '2010', 'EXTRATROPICAL CYCLONES']

    layers = ['eta', 'etavmax', 'u', 'v']
    styles = ['pcolor_average_jet_None_None_grid_False']

    resp = {}    

    storm = 'UNKNOWN'
    for strm in storms:
        if strm.lower() in uri.lower():
            storm = strm
            break

    nc = ncDataset(uri)
    dlayers = {}
    for layer in layers:
        if layer in nc.variables.keys():
            dlayers[layer] = 'pcolor_average_jet_None_None_grid_False'
    
    
    split_url = uri.split("/")
    resp['name']      = name
    resp['org_model'] = split_url[-2]
    resp['category']  = split_url[-3]
    resp['storm']     = storm
    resp['url']       = uri
    resp['layers']    = dlayers

    return resp

def insert_odp(records, **kwargs):
    """
    ARGS:
      records (OrderedDict) <str, wslib.csw.CswRecord>  output of CatalogueServiceWeb
    KWARGS:
      update_topology (bool) set true to create/update topologies of discovered odp endpoints
      title (string, default=legal_id) dataset title (human readable)
      abstract (string, default="") dataset abstract
      test_layer (string, default="")
      test_style (string, default="")
      keep_up_to_date (bool, default=True)
      display_all_timesteps (bool, default=False)
      
    MODIFIES:
        django database (wms_dataset table)
        (optionally):
            Will create/update topologies of discovered odp endpoints
            
    RETURNS:
        None
    """
    nrecords = len(records)
    logger.info("Parsing {0} records".format(nrecords))

    nsuccess_topology = 0
    nsuccess_load = 0
    for name, record in records.items():
        logger.debug("Processing record: {0}".format(name))
        
        # sciwms can't deal with dataset id/names that have these characters.
        # This is because the topology of each dataset is stored in a file
        # with with a filename that is the same as the dataset.name
        legal_id = re.sub('[ .!,;\-/\\\\]','_', name)

        for ref in record.references:
            if 'odp' in ref.get('scheme').split(":"):
                try:
                    d = ncDataset(ref['url'], 'r')
                    nsuccess_load += 1
                except:
                    logger.error("Couldn't load netCDF4 object for record {0} at ulr {1}".format(name,ref['url']))

                try:
                    if sciwmsDataset.objects.filter(name=legal_id).count():             
                        dataset            = sciwmsDataset.objects.get(name=legal_id)
                        dataset.title      = kwargs.get('title', name)
                        dataset.uri        = ref.get('url')
                        dataset.abstract   = kwargs.get('abstract', dataset.abstract)
                        dataset.test_layer = kwargs.get('test_layer', dataset.test_layer)
                        dataset.test_style = kwargs.get('test_style', dataset.test_style)
                        dataset.keep_up_to_date = \
                          kwargs.get('keep_up_to_date', dataset.keep_up_to_date)
                        dataset.display_all_timesteps =\
                            kwargs.get('display_all_timesteps', dataset.display_all_timesteps)
                                                
                        dataset.json = kwargs.get('json', json_helper(legal_id, dataset.uri))


                    else:
                        dataset = sciwmsDataset.objects.create(
                            name=legal_id, 
                            title=kwargs.get('title',name),
                            uri=ref.get('url',""), abstract = kwargs.get('abstract',""),
                            test_layer=kwargs.get('test_layer',""),
                            test_style=kwargs.get('test_style',""),
                            keep_up_to_date=kwargs.get('keep_up_to_date', True),
                            display_all_timesteps=kwargs.get('display_all_timesteps',""))
                        dataset.json=kwargs.get('json',json_helper(legal_id,dataset.uri))
                    
                    dataset.save()

                    logger.info("json = {0}".format(json.dumps(dataset.json)))
                    if kwargs.get('update_topology', False):
                        update_dataset_cache(dataset)
                        nsuccess_topology += 1
                except:
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    logger.error(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)) +\
                                 "\nCouldn't Find/Create Django DB object for {0}".format(legal_id))
                
                # can only handle datasets with a single endpoint
                break

    logger.info("Successfully loaded {0} of {1} endpoints.".format(nsuccess_load, nrecords))

    jlist = []
    for d in sciwmsDataset.objects.all():
        jlist.append(d.json)

    json_row = "json_all"
    dataset = sciwmsDataset.objects.filter(name=json_row)
    if len(dataset) == 0:
        dataset = sciwmsDataset.objects.create(
            name=json_row,
            title="",
            uri="",
            abstract="",
            test_layer="",
            test_style="",
            keep_up_to_date=False,
            display_all_timesteps=False)

    else:
        dataset = dataset[0]

    j = []
    for d in sciwmsDataset.objects.filter(~Q(name=json_row)):
        print "Aggregating json from {0}".format(d.name)
        j.append(d.json)

    dataset.json=j
    dataset.save()

    
    if(kwargs.get('update_topology')):
        logger.info("Succesfully updated {0} of {1} topologies.".format(nsuccess_topology,nrecords))

def index_csw(endpoint = None, isequal_constraints=[],
              timeout = 120, maxrecords = 999999,
              insert_djangodb = False, update_topology=False):
    """
    Creates csw.CatalogueServiceWeb object and fes filter from two input strings
    REQUIRED KEYWORD ARGS:
        endpoint (string) url to csw catalogue

        isequal_constraints (list(string,string)) A list of string tuples
            The list of strings will be used to create a list of fes.PropertyIsEqualTo constraints.
            The first string will be passed to the constructor's "propertyname" argument
            the second will be passed to the constructor's "literal" argument.
            
        bool update_cache (bool) create/update topologies for discovered datasets
        
    OPTIONAL:
        timeout           (int) timeout for csw catalogue (default 120)
        maxrecords        (int) max records for csw.getrecords2 (default 999999)
        insert_djangodb   (bool) optionally insert fetched OpenDAP endpoints into django db
        update_topology   (bool) optionally create/update cached topology for OpenDAP endpoint
        
    MODIFIES (optionally):
        django wms_dataset database
        (optionally) Create/update topologies for discovered OpenDAP endpoints
        
    RETURNS:
        csw.CatalogueServiceWeb

    EXAMPLE USAGE:
         enpoint = "http://www.ngdc.noaa.gov/geoportal/csw"
         constraint_pairs = [('sys.siteuuid','8BF00750-66C7-49FF-8894-4D4F96FD86C0')]
         csw_catalogue = index_csw_odp(endpoint, constraint_pairs)
    """   
    request_cnt = 0
    while request_cnt < 2:
        try:
            logger.info("Querying CSW Catalog {0} attempt {1}".format(endpoint, request_cnt+1))
            csw_catalogue = csw.CatalogueServiceWeb(endpoint, timeout = timeout)
            break
        except:
            #try one more time, timeouts sometimes occur
            logger.info("Couldn't parse catalog on first pass, trying again.")
            import time
            time.sleep(30)#give the server some extra time
            csw_catalogue = csw.CatalogueServiceWeb(endpoint, timeout = timeout)
            request_cnt += 1

    if request_cnt == 2:
        logger.info("Couldn't contact {0}".format(endpoint))
        return

    isequal_filters = []
    if isequal_constraints:
        for cpair in isequal_constraints:
            if len(cpair) == 2:
                isequal_filters.append(fes.PropertyIsEqualTo(
                    propertyname='{0}'.format(cpair[0]),
                    literal="{{{0}}}".format(cpair[1])))
            else:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logger.error(repr(traceback.format_exception(exc_type, exc_value, exc_traceback)) +\
                             "\nDimension Mismatch - Cannot create filter from {0}".format(cpair))

    
    csw_catalogue.getrecords2(isequal_filters, esn='full', maxrecords=999999)
    logger.info("Found {0} records".format(len(csw_catalogue.records)))

    if insert_djangodb:
        insert_odp(csw_catalogue.records, update_topology=update_topology)
        
    return csw_catalogue
