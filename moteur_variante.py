from interface_py import moteur_variante as _mod


def __getattr__(name):
    return getattr(_mod, name)


def __setattr__(name, value):
    setattr(_mod, name, value)


if __name__ == "__main__":
    _mod.main()
