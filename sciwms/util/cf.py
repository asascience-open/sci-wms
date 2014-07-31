import re

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

