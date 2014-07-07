from django.conf import settings
import logging
import multiprocessing
import os

output_path = os.path.join(settings.PROJECT_ROOT, 'logs', 'sciwms_wms.log')
# Set up Logger
logger = multiprocessing.get_logger()
#logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(output_path)
formatter = logging.Formatter(fmt='[%(asctime)s] - <<%(levelname)s>> - |%(message)s|')
handler.setFormatter(formatter)
logger.addHandler(handler)


def run():

    #print "Updating datasets..."
    #from sciwms.libs.data.caching import update_datasets
    #try:
    #    update_datasets()
    #except BaseException:
    #    print '\n    ###################################################\n' +\
    #          '    #                                                 #\n' +\
    #          '    #  There was a problem initializing some of your  #\n' +\
    #          '    #  datasets.  Please see the log for more details #\n' +\
    #          '    #                                                 #\n' +\
    #          '    ###################################################\n'

    print '\n    ##################################################\n' +\
          '    #                                                #\n' +\
          '    #  Starting sci-wms...                           #\n' +\
          '    #  A wms server for unstructured scientific data #\n' +\
          '    #                                                #\n' +\
          '    ##################################################\n'
