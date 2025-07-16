from interface_py import settings_manager as _mod


def __getattr__(name):
    return getattr(_mod, name)


def __setattr__(name, value):
    setattr(_mod, name, value)
