class DictConfig(object):
    _final_config = None

    def __len__(self):
        self._set_final_config()
        return self._final_config.__len__()

    def __length_hint__(self):
        self._set_final_config()
        if hasattr(self._final_config, "__length_hint__"):
            return self._final_config.__length_hint__()
        return None

    def __getitem__(self, key):
        self._set_final_config()
        return self._final_config.__getitem__(key)

    def __missing__(self, key):
        self._set_final_config()
        return self._final_config.__missing__(key)

    def __setitem__(self, key, value):
        self._set_final_config()
        return self._final_config.__setitem__(key, value)

    def __delitem__(self, key):
        self._set_final_config()
        return self._final_config.__delitem__(key)

    def __iter__(self):
        self._set_final_config()
        return self._final_config.__iter__()

    def __reversed__(self):
        self._set_final_config()
        return self._final_config.__reversed__()

    def __contains__(self, item):
        self._set_final_config()
        return self._final_config.__contains__(item)

    def items(self):
        self._set_final_config()
        return self._final_config.items()

    def keys(self):
        self._set_final_config()
        return self._final_config.keys()

    def values(self):
        self._set_final_config()
        return self._final_config.values()

    def _set_final_config(self):
        self._final_config = {}
