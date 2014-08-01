import re

map = {
   'time': {'standard_name':'time'},
   'longitude': {'standard_name':'longitude', 'scale_min':'0', 'scale_max':'360'},
   'latitude': {'standard_name':'latitude', 'scale_min':'-90', 'scale_max':'90'},
   'ssh_geoid': {'standard_name':'sea_surface_height_above_geoid', 'scale_min':'0', 'scale_max':'7.0'},
   'ssh_reference_datum': {'standard_name':'water_surface_height_above_reference_datum', 'scale_min':'0', 'scale_max':'7.0'},
   'u': {'standard_name':'eastward_sea_water_velocity', 'scale_min':'0', 'scale_max':'2'},
   'v': {'standard_name':'northward_sea_water_velocity', 'scale_min':'0', 'scale_max':'2'},
   'hs': {'standard_name':'sea_surface_wave_significant_height', 'scale_min':'0', 'scale_max':'12'},
   'uwind': {'standard_name':'eastward_wind', 'scale_min':'0', 'scale_max':'80'},
   'vwind': {'standard_name':'northward_wind', 'scale_min':'0', 'scale_max':'80'},
   'salinity': {'standard_name':'sea_walter_salinity', 'scale_min':'32', 'scale_max':'37'},
   'sst': {'standard_name':'sea_water_temperature', 'scale_min':'20', 'scale_max':'30'},
}

def get_by_standard_name(nc, standard_name):
    for vn, v in nc.variables.iteritems():
        # sn - standard_name
        sn = nc.variables[vn].__dict__.get('standard_name', None)
        if sn == None:
            continue
        # cm - cell_methods
        cm = nc.variables[vn].__dict__.get('cell_methods', None)
        # if cell_method specified, prepend method to key
        if cm != None:
            cm = re.sub(":\s+", "_", cm)
            cm = re.sub("\s+", "", cm)
            sn = '%s_%s' % (cm, sn)
        if sn == standard_name:
            return v
    return None

def nc_name_from_standard(nc, standard_name):
    """
    Reverse lookup from standard name to nc name.
    """
    ret = None
    for k, v in nc.variables.iteritems():
        if standard_name == v.__dict__.get('standard_name'):
            ret = k
            break
    return ret
            
def get_global_attribute(nc, attr):
    """
    Wrapper to return None if attr DNE.
    attr is a string
    """
    try:
        ret = getattr(nc,attr)
    except:
        ret = None
    return ret

