"""
Here be utils.

.%%..%%..%%%%%%..%%%%%%..%%.......%%%%..
.%%..%%....%%......%%....%%......%%.....
.%%..%%....%%......%%....%%.......%%%%..
.%%..%%....%%......%%....%%..........%%.
..%%%%.....%%....%%%%%%..%%%%%%...%%%%..
........................................

"""

import hashlib
from paco.core.exception import StackException, PacoErrorCode
from paco.models import schemas
from paco.models.locations import get_parent_by_interface
from copy import deepcopy
from functools import partial
from hashlib import blake2b


def hash_smaller(text, max_len=99):
    "Return a string that is shorter than 100 chars by hashing the start"
    if len(text) <= max_len:
        return text
    digest_size = 8
    hash_sig = blake2b(
        bytearray(text, 'utf-8'),
        digest_size=digest_size
    ).hexdigest()
    # hexdigest is twice length of the digest size
    # leave an extra char for a '-' seperator.
    hex_len = (max_len - 1) - (digest_size * 2)
    return hash_sig + '-'  + text[-hex_len:]

def md5sum(filename=None, str_data=None):
    """Computes and returns an MD5 sum in hexdigest format on a file or string"""
    d = hashlib.md5()
    if filename != None:
        with open(filename, mode='rb') as f:
            for buf in iter(partial(f.read, 128), b''):
                d.update(buf)
    elif str_data != None:
        d.update(bytearray(str_data, 'utf-8'))
    else:
        raise StackException(PacoErrorCode.Unknown, message="cli: md5sum: Filename or String data expected")

    return d.hexdigest()

def dict_of_dicts_merge(x, y):
    """Merge to dictionaries of dictionaries"""
    z = {}
    if hasattr(x, 'keys') == False or hasattr(y, 'keys') == False:
        return y
    overlapping_keys = x.keys() & y.keys()
    for key in overlapping_keys:
        z[key] = dict_of_dicts_merge(x[key], y[key])
    for key in x.keys() - overlapping_keys:
        z[key] = deepcopy(x[key])
    for key in y.keys() - overlapping_keys:
        z[key] = deepcopy(y[key])
    return z

def str_spc(str_data, size):
    "Add space padding to a string"
    new_str = str_data
    str_len = len(str_data)
    if str_len > size:
        message = "ERROR: cli: str_spc: string size is larger than space size: {0} > {1}".format(
            str_len, size
        )
        raise StackException(PacoErrorCode.Unknown, message = message)

    for idx in range(size - str_len):
        new_str += " "
    return new_str

def big_join(str_list, separator_ch, camel_case=False, none_value_ok=False):
    # Duplicated in paco.models.base.Resource
    # Camel Case
    new_str = ""
    first = True
    for str_item in str_list:
        if none_value_ok == True and str_item == None:
            continue
        if first == False:
            new_str += separator_ch
        if camel_case == True:
            new_str += str_item[0].upper()+str_item[1:]
        else:
            new_str += str_item
        first = False
    return new_str

def prefixed_name(resource, name, legacy_flag):
    """Returns a name prefixed to be unique:
    e.g. netenv_name-env_name-app_name-group_name-resource_name-name"""
    str_list = []
    # currently ony works for resources in an environment
    if legacy_flag('netenv_loggroup_name_2019_10_13') == False:
        netenv_name = get_parent_by_interface(resource, schemas.INetworkEnvironment).name
        str_list.append(netenv_name)
    env_name = get_parent_by_interface(resource, schemas.IEnvironment).name
    app_name = get_parent_by_interface(resource, schemas.IApplication).name
    group_name = get_parent_by_interface(resource, schemas.IResourceGroup).name

    str_list.extend([env_name, app_name, group_name, resource.name, name])

    return '-'.join(str_list)


def log_action(action, message, return_it=False, enabled=True):
    log_message = action+": "+message
    if enabled == False:
        log_message = '! Disabled: ' + log_message
    if return_it == False:
        print(log_message)
    else:
        return log_message

def list_to_comma_string(list_to_convert):
    "Converts a list to a comma-seperated string"
    comma=''
    str_list = ""
    for item in list_to_convert:
        str_list += comma + item
        comma = ','
    return str_list