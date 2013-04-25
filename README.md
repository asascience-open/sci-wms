sci-wms
=========
COPYRIGHT 2010 Alexander Crosby

####A Python WMS service for geospatial gridded data (Only unstructured FVCOM and ADCIRC grids and structured grids officially supported)

![Global HYCOM as filled contours](https://raw.github.com/acrosby/sci-wms/master/src/pywms/wms/static/example1.png)

##System Requirements

- >= 4GB RAM But it depends directly on the size and extents of the datasets you will be visualizing.
- > 2 CPU (> 4 CPU Better) 
- Version 3 > Python > Version 2.6
- LibGeos (http://download.osgeo.org/geos/)
- LibSpatialIndex (http://libspatialindex.github.com)

##Community

[We have started a Google Group for the sci-wms project located here.](https://groups.google.com/forum/?fromgroups#!forum/sci-wms)

##Install

[Download the compressed project and unpack anywhere.](http://acrosby.github.com/sci-wms) This is where the installation will live.

####If you have the standard enthought python distribution (epd):

Install the remaining dependencies:

    $easy_install gunicorn
    $easy_install greenlet
    $easy_install gevent              # or easy_install eventlet
    $easy_install django

####If are not using the enthought python distribution:

You must have the following python packages installed:

- django (>= 1.4 preferred)
- gunicorn
- greenlet
- gevent or eventlet
- numpy
- matplotlib (>= 1.2.0)
- matplotlib basemap (>= 1.0.6)
- netCDF4 (Install from the netcdf4-python google code repository if using a recent build of HDF5)
- shapely
- rtree

sci-wms works with both pip and virtualenv quite happily. If you
have pip installed you can use the following to install many (but not all) of the required modules:

    $pip install package

<!---
Or you can install the required packages (with the versions we develop
the wms on) with the requirements file:

    $pip install -r requirements.txt
-->

Similarly if you have setup_tools installed you can use:

    $easy_install package

If you are using virtualenv, just make sure you have the environment
activated before you try to install the packages or point to the environment
with pip on the install command.

You also need to ensure that you have basemap matplotlib toolkit installed:

    $wget -o basemap-1.0.6.tar.gz http://sourceforge.net/projects/matplotlib/files/matplotlib-toolkits/basemap-1.0.6/basemap-1.0.6.tar.gz/download
    $pip install basemap-1.0.6.tar.gz


###Caveats:

Look at https://github.com/acrosby/sci-wms/issues?state=open for a list of known issues and problems.

