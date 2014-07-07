import os
import multiprocessing
import sys
import traceback

import pyproj

from django.conf import settings

logger = multiprocessing.get_logger()

def print_exception(log=logger):
    exc_type, exc_value, exc_traceback = sys.exc_info()
    log.error("ERROR: " + repr(traceback.format_exception(exc_type, exc_value, exc_traceback)))

def get_pyproj(request):
    try:
        projstr = request.GET["crs"]
    except:
        try:
            projstr = request.GET["srs"]
        except:
            projstr = "EPSG:3857"
            logger.debug("Projection not specified using default mercator {0}".format(projstr))
    #logger.debug(projstr)
    return pyproj.Proj(init=projstr)

def get_rtree_nodes_path(dataset_name):
    """
    Return the root, idx and dat path of the node rtree index
    for a given dataset name
    """
    nodes_root = os.path.join(settings.TOPOLOGY_PATH, dataset_name + "_nodes")
    idx_path = nodes_root + '.idx'
    dat_path = nodes_root + '.dat'
    return nodes_root, idx_path, dat_path

def rtree_nodes_exists(dataset_name):
    """
    Return True if there is a node rtree index for the given dataset_name.
    Return False otherwise
    """
    nodes_path, idx_path, dat_path = get_rtree_nodes_path(dataset_name)
    logger.debug("rtree_nodes_exists::os.path.exists(idx_path) is {0}".\
                 format(os.path.exists(idx_path)))
    logger.debug("rtree_nodes_exists::os.path.exists(dat_path) is {0}".\
                 format(os.path.exists(dat_path)))
    
    return os.path.exists(idx_path) == True and os.path.exists(dat_path) == True

def get_rtree_cells_path(dataset_name):
    """
    Return the root, idx and dat path of the cell (faces) rtree index
    for a given dataset name
    """
    cells_root = os.path.join(settings.TOPOLOGY_PATH, dataset_name + "_cells")
    idx_path = cells_root + '.idx'
    dat_path = cells_root + '.dat'
    return cells_root, idx_path, dat_path

def rtree_cells_exists(dataset_name):
    """
    Return True if there is a node rtree index for the given dataset_name.
    Return False otherwise
    """
    cells_root, idx_path, dat_path = get_rtree_cells_path(dataset_name)
    return os.path.exists(idx_path) == True and os.path.exists(dat_path) == True
    
    
    
    

        
