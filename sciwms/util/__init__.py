import pyproj
import multiprocessing
logger = multiprocessing.get_logger()

def get_pyproj(request):
    logger.debug("in get_proj")
    try:
        projstr = request.GET["CRS"]
        logger.debug("projection CRS: {0}".format(projstr))
    except:
        try:
            projstr = request.GET["SRS"]
            logger.debug("projection CRS: {0}".format(projstr))
        except:
            projstr = "EPSG:3857"
            logger.debug("Projection not specified using default mercator {0}".format(projstr))
            
    logger.debug("sciwms.util.get_pyproj projstr = {0}".format(projstr))
    
    return pyproj.Proj(init=projstr)
    
    

        
