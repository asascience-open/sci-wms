import os
import re
import netCDF4
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sciwms.settings.defaults")
from django.conf import settings
from sciwms.util import cf
import numpy as np
import pyugrid

def spatial_extent(nc):
    try:
        ug = pyugrid.UGrid.from_ncfile(nc)
        longitude = ug.nodes[:,0]
        latitude = ug.nodes[:,1]
    except:
        longitude = cf.get_by_standard_name(nc, 'longitude')
        latitude = cf.get_by_standard_name(nc, 'latitude')
        if longitude is None or latitude is None:
            return []
        longitude = longitude[:]
        latitude = latitude[:]
    return [np.nanmin(longitude), np.nanmin(latitude), np.nanmax(longitude), np.nanmax(latitude)]

def temporal_extent(nc):
    temporal_extent = []
    time = cf.get_by_standard_name(nc, 'time')
    if time:
        units = time.units
        calendar = time.calendar if hasattr(time, 'calendar') else None
        dates = []
        for t in time[:]:
            if calendar is None:
                dates.append(netCDF4.num2date(t, units))
            else:
                dates.append(netCDF4.num2date(t, units, calendar))
        if len(dates):
            temporal_extent = [dates[0].isoformat(), dates[-1].isoformat()]
    return temporal_extent

# ------------------------
# TODO: COMT specific code
# ------------------------
ignore = ['time', 'latitude', 'longitude', 'depth']
def get_layers(nc):

    # return dict: key is NetCDF variable name, value is standard_name, empty if no-standard name (so user can supply it)
    layers = {}

    # NetCDF variables, if standard_name exists and is in util/cf default_scales, add, else, we ignore
    for vn, v in nc.variables.iteritems():
        # skip variables with a single dimension (not plottable)
        if v.ndim == 1:
            continue
        sn = getattr(v, 'standard_name', None)
        ln = getattr(v, 'long_name', None)
        units = getattr(v, 'units', None)
        if sn:
            sn = sn.lower()
        if sn not in cf.standard_names:
            #print "unknown standard_name {0}".format(sn)
            sn = None
        if sn in cf.default_scales.keys():
            min, max = cf.default_scales.get(sn, None)
            style = "contourf_average_jet_%s_%s_grid_False" % (min, max)
        else:
            style = None
        # TODO: look up default range for standard_name and units
        #print '\t\tadding %s (NetCDF var) with LAYER name (CF standard_name) %s' % (vn, sn)
        layers[vn] = {'standard_name': sn, 'long_name': ln, 'units': units, 'style': style}

    # make sure no [time,latitude,longitude] TODO: handled with ignore
    #layers.pop('time', None)
    #layers.pop('latitude', None)
    #layers.pop('longitude', None)

    # ------------------------------------
    # VECTORS (contain eastward/northward)
    # ------------------------------------
    # TODO: examine best way to do this w/ CF
    add_layers = {}
    remove_layers = []
    for eastward_vn in layers:
        eastward_sn = layers[eastward_vn].get('standard_name', None)
        if eastward_sn:
          if 'eastward' in eastward_sn:
              # look for northward
              for northward_vn in layers:
                  northward_sn = layers[northward_vn].get('standard_name', None)
                  if northward_sn == eastward_sn.replace('eastward', 'northward'):
                      name = eastward_sn.replace('eastward_', '')
                      units = layers[eastward_vn].get('units', None)
                      style = layers[eastward_vn].get('style', None).replace('contourf', 'quiver')
                      # new layer, use standard_name without eastward/northward for "variable name"
                      add_layers[name] = {'standard_name': '%s,%s' % (eastward_sn,northward_sn), 'long_name': name, 'units': units, 'style': style}
                      remove_layers.append(eastward_vn)
                      remove_layers.append(northward_vn)                    
    for k in add_layers:
        layers[k] = add_layers[k]
        #print '\t\tadded %s' % k
    for k in remove_layers:
        del layers[k]
        #print '\t\tremoved %s' % k

    return layers
