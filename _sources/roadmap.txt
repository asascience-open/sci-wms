Roadmap
=======

SCI-WMS is funded by a number of organizations to fufill the specific 
needs of the Metorology and Oceanography communities. We are 
committed to ensuring that the project follows a logical and innovative 
path, but due to time and budget constraints some enhancements and 
updates will take precedence over others.

We welcome discussion of problems and suggestions for new features at 
the `SCI-WMS Google Group <https://groups.google.com/forum/?fromgroups#!forum/sci-wms>`_. 
Enhancements that have been accepted by the team for inclusion into the project can 
be found at the project Github `repository <https://github.com/asascience-open/sci-wms/issues?state=open>`_.

===================
Current (|release|)
===================

We are currently trying to eliminate some of the major bugs, that are within our control to fix. 
We are also trying to firm up the functionality and api components before the release of version 1.0.0.

We have recently:

* Added service based api to dataset and group management
* Solved the dataset topology cache update problem with daemons falling down
* Added command line topology cache update command
* Added jsonp responses to avoid clients from needing to proxy xml responses
* Added test procedures
* Added support for mutiple fill values via additional variable attribute in dataset
* We now have generic config files for nginx, upstart and supervisor in addition to the gunicorn config that has always been in the project

===============
Version 1.0.0
===============

The target for Version 1.0.0 is a server that is:

* Well documented
* Easy to install
* Easy to administer
* Stable

=============
Version 1.1.0
=============

=============
Version 1.2.0
=============

By this version we would like to see solid support for all 
netCDF/openDAP datasets that can be expressed by CF, 
anything that is not supported will be considered a bug.

=============
Version 2.0.0
=============

The aim for this version is to provide a plug-able framework for creating styles, to allow users and clients to come up with their own and distribute.

================================
Goals not assigned to a version
================================

* Topology cache into hdf5 file, instead many different files for each dataset
* Better support for unconventional but CF compliant datasets
* `Styles that express uncertainty, like in climate modeling <https://github.com/asascience-open/sci-wms/issues/77>`_
* Support for projections in addition to Web Mercator
* `Support for CF Discrete Sampling Geometries <https://github.com/asascience-open/sci-wms/issues/65>`_
* `Support for ROMS style staggered grid representations <https://github.com/asascience-open/sci-wms/issues/63>`_
* `Support for native SWAN (non UGRID-CF) output <https://github.com/asascience-open/sci-wms/issues/62>`_
* `Scripts to automatically add datasets to server from various cataloging systems <https://github.com/asascience-open/sci-wms/issues/22>`_
* `Add support for hardware based rendering on machines capable of it <https://github.com/asascience-open/sci-wms/issues/15>`_
* Integration with advanced HTML5 browser-based visualization tools
* Support for HDF5 (local and raw, i.e. not netCDF4) datasets that are CF compliant
