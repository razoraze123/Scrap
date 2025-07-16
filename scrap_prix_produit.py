from interface_py import scrap_price as _mod


def __getattr__(name):
    return getattr(_mod, name)


def __setattr__(name, value):
    setattr(_mod, name, value)


if __name__ == "__main__":
    _mod.main()
