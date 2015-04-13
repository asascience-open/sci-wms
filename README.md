#SCI-WMS

###Python Web Mapping Service (WMS) for visualizing geospatial data

* SCI-WMS is an open-source Python implementation of the (Web Mapping Service) API for oceanographic, atmospheric, climate and weather data.
* Achieves real-time, on-demand visualization of externally hosted CF-compliant data.
* Can visualize structured or unstructured grids adhering to CF and/or CF-UGRID conventions.
* Abstracts each dataset into two objects: a topology and corresponding model data.
* Topologies are stored locally for quick and efficient spatial queries.
* Model data is hosted externally, subsetted data is downloaded and rendered per request.
* Supports arbitrary cartographic projections.

##System Requirements

* >= 4GB RAM suggested, topology generation can impact system if low RAM

## Project Homepage
[SCI-WMS](http://asascience-open.github.io/sci-wms/)

##Documentation/Installation

[SCI-WMS 0.1.0 documentation](http://asascience-open.github.io/sci-wms/docs/index.html)

COPYRIGHT 2010 RPS ASA

    SCI-WMS is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    SCI-WMS is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with SCI-WMS.  If not, see <http://www.gnu.org/licenses/>.
