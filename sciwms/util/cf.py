import re

# CF standard_name and the default scale to be applied to its display
default_scales = {
    'sea_surface_height_above_geoid':             [0.0, 7.0],
    'water_surface_height_above_reference_datum': [0.0, 7.0],
    'eastward_sea_water_velocity':                [0.0, 2.0],
    'northward_sea_water_velocity':               [0.0, 2.0],
    'sea_surface_wave_significant_height':        [0.0, 12.0],
    'eastward_wind':                              [0.0, 80.0],
    'northward_wind':                             [0.0, 80.0],
    'sea_water_salinity':                         [0.0, 37.0],
    'sea_water_temperature':                      [0.0, 40.0],
    'barotropic_eastward_sea_water_velocity': [0.0, 2.0],
    'barotropic_northward_sea_water_velocity': [0.0, 2.0],
    'mass_concentration_of_oxygen_in_sea_water': [0.0,16.0],
    'mole_concentration_of_nitrate_in_sea_water': [0.0, 55.0],
    'mole_concentration_of_organic_detritus_expressed_as_nitrogen_in_sea_water': [0.0, 0.1],
    'mole_concentration_of_phytoplankton_expressed_as_nitrogen_in_sea_water': [0.0, 0.1],
    'mole_concentration_of_mesozooplankton_expressed_as_nitrogen_in_sea_water': [0.0, 0.1],
    'mass_concentration_of_chlorophyll_in_sea_water': [0.0, 0.1],
}

long_names = {
    'time': 'time since initialization',
    'longitude': 'longitude of RHO-points',
    'latitude': 'latitude of RHO-points',
    'mole_concentration_of_nitrate_in_sea_water': 'nitrate concentration',
    'mole_concentration_of_organic_detritus_expressed_as_nitrogen_in_sea_water': 'detritus concentration',
    'mole_concentration_of_phytoplankton_expressed_as_nitrogen_in_sea_water': 'phytoplankton concentration',
    'mole_concentration_of_mesozooplankton_expressed_as_nitrogen_in_sea_water': 'zooplankton concentration',
    'mass_concentration_of_chlorophyll_in_sea_water': 'chlorophyll concentration',
    'sea_water_temperature': 'potential temperature',
    'sea_water_salinity': 'salinity',
}

# TODO: remove, should be unused BM 20141210
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
   'salinity': {'standard_name':'sea_water_salinity', 'scale_min':'32', 'scale_max':'37'},
   'sst': {'standard_name':'sea_water_temperature', 'scale_min':'0', 'scale_max':'40'},
   'ubarotropic': {'standard_name':'barotropic_eastward_sea_water_velocity', 'scale_min':'0', 'scale_max':'2'},
   'vbarotropic': {'standard_name':'barotropic_northward_sea_water_velocity', 'scale_min':'0', 'scale_max':'2'},
}

def get_by_standard_name(nc, standard_name):
    """
    returns netCDF variable object
    """
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
    '''
    BM 20141211 this is a hack, datasets are not using the standard_name CF convention regularly
    check known long names
    uses above long_names to attempt to locate variables with no standard_name attribute
    '''
    long_name = long_names.get(standard_name, None)
    if long_name is None:
        return None
    for vn, v in nc.variables.iteritems():
        ln = nc.variables[vn].__dict__.get('long_name', None)
        if ln == None:
            continue
        if ln == long_name:
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

