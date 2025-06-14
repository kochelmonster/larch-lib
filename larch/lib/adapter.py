"""
Provides a Registry class to register and retrieving adapters
"""
import inspect


class _THROW_EXCEPTION:
    pass


# __pragma__ ('ecom')
"""?
def to_register_key(key):
    ft, tt, style = key
    return f"{ft.__name__}:{ft.__module__}-{tt.__name__}:{tt.__module__}-{style}"
?"""


class Registry:
    """A type dependent registry"""

    def __init__(self):
        self.values = {}
        """all adapters in registry, (also the cached ones)"""
        self.registered = {}
        """only registered adapters"""

    def register(self, from_type, to_type, style, value, replace=False):
        """registers a value"""
        key = from_type, to_type, style
        """?
        key = to_register_key(key)
        ?"""
        if (not replace
                and self.values.get(key, _THROW_EXCEPTION)
                is not _THROW_EXCEPTION):
            raise ValueError("value already exists", (from_type, to_type, style))

        self.values[key] = self.registered[key] = value

    def get(self, from_type, to_type, style="", default=_THROW_EXCEPTION):
        """retrieves a factory for a "from_type to to_type adapter
        style can be used to specify adapter. style can be grouped
        with "." (dots). (see test)
        Caches inferenced adapters.
        """
        def return_default():
            if default is not _THROW_EXCEPTION:
                return default

            raise ValueError("Cannot find factory", from_type, to_type, style)

        values = self.values
        key = from_type, to_type, style
        """?
        key = to_register_key(key)
        ?"""
        try:
            v = values[key]
            return return_default() if v is _THROW_EXCEPTION else v
        except KeyError:
            pass

        def iter_style(style):
            last_style = None
            while last_style != style:
                last_style = style
                yield style
                style = style.rsplit(".", 1)[0]

            yield ""

        registered = self.registered
        bases = inspect.getmro(from_type)
        for substyle in iter_style(style):
            for b in bases:
                key = b, to_type, substyle
                """?
                key = to_register_key(key)
                ?"""
                found = registered.get(key)
                if found is not None:
                    # the next time it will be fast
                    v = values[from_type, to_type, style] = found
                    return v

        values[from_type, to_type, style] = _THROW_EXCEPTION
        return return_default()


registry = Registry()
register = registry.register
get = registry.get

# __pragma__ ('noecom')
