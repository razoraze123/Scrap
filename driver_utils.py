from interface_py import driver_utils as _mod

def __getattr__(name):
    return getattr(_mod, name)

def __setattr__(name, value):
    setattr(_mod, name, value)
