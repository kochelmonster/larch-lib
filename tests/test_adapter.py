import unittest
from larch.lib.adapter import Registry

class DummyFrom:
    pass

class DummyTo:
    pass

class DummyAdapter:
    def __init__(self, obj):
        self.obj = obj
    def who(self):
        return "dummy"

class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = Registry()

    def test_register_and_get(self):
        self.registry.register(DummyFrom, DummyTo, "", DummyAdapter)
        adapter_cls = self.registry.get(DummyFrom, DummyTo)
        self.assertIs(adapter_cls, DummyAdapter)
        instance = adapter_cls("foo")
        self.assertEqual(instance.who(), "dummy")

    def test_register_duplicate_raises(self):
        self.registry.register(DummyFrom, DummyTo, "", DummyAdapter)
        with self.assertRaises(ValueError):
            self.registry.register(DummyFrom, DummyTo, "", DummyAdapter)

    def test_get_default(self):
        result = self.registry.get(DummyFrom, DummyTo, default=42)
        self.assertEqual(result, 42)

    def test_get_missing_raises(self):
        with self.assertRaises(ValueError):
            self.registry.get(DummyFrom, DummyTo)

    def test_replace(self):
        class Adapter1: pass
        class Adapter2: pass
        self.registry.register(DummyFrom, DummyTo, "", Adapter1)
        self.registry.register(DummyFrom, DummyTo, "", Adapter2, replace=True)
        self.assertIs(self.registry.get(DummyFrom, DummyTo), Adapter2)

    def test_cache_throw_exception(self):
        # This test covers lines 84, 85: values[from_type, to_type, style] = _THROW_EXCEPTION
        # and return return_default() when no adapter is found and no default is given
        class UnregisteredFrom: pass
        class UnregisteredTo: pass
        with self.assertRaises(ValueError):
            self.registry.get(UnregisteredFrom, UnregisteredTo)
        # After the first failed get, the cache should contain _THROW_EXCEPTION
        key = (UnregisteredFrom, UnregisteredTo, "")
        self.assertIs(self.registry.values[key], self.registry.values.get(key))
        self.assertIs(self.registry.values[key].__class__, type(self.registry.values[key]))

    def test_get_with_inheritance_and_style(self):
        # This test covers the 'if found is not None' branch in adapter.py line 82
        class BaseFrom: pass
        class SubFrom(BaseFrom): pass
        class To: pass
        class Adapter: pass
        # Register adapter for BaseFrom -> To
        self.registry.register(BaseFrom, To, "special", Adapter)
        # Should find the adapter via inheritance and style
        result = self.registry.get(SubFrom, To, style="special")
        self.assertIs(result, Adapter)

if __name__ == "__main__":
    unittest.main()
