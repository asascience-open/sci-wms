import re

from lxml import etree
# CF conventions (standard_names)
cf_standard_name_table = 'cf-standard-name-table.xml' # TODO path
doc = etree.parse(cf_standard_name_table)
version = doc.find('version_number')
standard_names = []
entries = doc.findall('//entry')
for entry in entries:
    if 'id' in entry.attrib:
        standard_names.append(entry.get('id'))


# CF standard_name and the default scale to be applied to its display
default_scales = {
    'sea_surface_height_above_geoid':             [0.0, 7.0],
    'water_surface_height_above_reference_datum': [0.0, 7.0],
    'eastward_sea_water_velocity':                [0.0, 1.0],
    'northward_sea_water_velocity':               [0.0, 1.0],
    'sea_surface_wave_significant_height':        [0.0, 12.0],
    'eastward_wind':                              [0.0, 40.0],
    'northward_wind':                             [0.0, 40.0],
    'sea_water_salinity':                         [0.0, 37.0],
    'sea_water_temperature':                      [0.0, 40.0],
    'barotropic_eastward_sea_water_velocity': [0.0, 1.0],
    'barotropic_northward_sea_water_velocity': [0.0, 1.0],
    'mass_concentration_of_oxygen_in_sea_water': [0.0,16.0],
    'mole_concentration_of_nitrate_in_sea_water': [0.0, 55.0],
    'mole_concentration_of_organic_detritus_expressed_as_nitrogen_in_sea_water': [0.0, 0.1],
    'mole_concentration_of_phytoplankton_expressed_as_nitrogen_in_sea_water': [0.0, 0.1],
    'mole_concentration_of_mesozooplankton_expressed_as_nitrogen_in_sea_water': [0.0, 0.1],
    'mass_concentration_of_chlorophyll_in_sea_water': [0.0, 0.1],
}

long_names = {
    'time': ['time', 'time since initialization'],
    'longitude': ['longitude of RHO-points'],
    'latitude': ['latitude of RHO-points'],
    'mole_concentration_of_nitrate_in_sea_water': ['nitrate concentration'],
    'mole_concentration_of_organic_detritus_expressed_as_nitrogen_in_sea_water': ['detritus concentration'],
    'mole_concentration_of_phytoplankton_expressed_as_nitrogen_in_sea_water': ['phytoplankton concentration'],
    'mole_concentration_of_mesozooplankton_expressed_as_nitrogen_in_sea_water': ['zooplankton concentration'],
    'mass_concentration_of_chlorophyll_in_sea_water': ['chlorophyll concentration'],
    'sea_water_temperature': ['potential temperature'],
    'sea_water_salinity': ['salinity'],
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
    BM 20141211 this is a hack
    datasets are not using the standard_name CF convention regularly
    check known long names (above) before returning None
    '''
    long_name = long_names.get(standard_name, None) # array of known long names for this sn
    if long_name is None:
        return None # no known long names for this standard_name
    for vn, v in nc.variables.iteritems():
        ln = nc.variables[vn].__dict__.get('long_name', None)
        if ln == None:
            continue
        if ln in long_name:
            return v
    return None
