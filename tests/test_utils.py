# -*- coding: utf-8 -*-
"""
Tests the serval modules in larch.db.kernel
"""
import os
import sys
import logging
import io
import unittest
import yaml
from larch.lib.gevent import _DebounceContext
from larch.lib.utils import (
    to_utf8, to_unicode, pyeval, deep_update, string_to_obj,
    try_until_timeout, PerformanceHistory, pid_exists)
from larch.lib import utils


class UtilsTest(unittest.TestCase):
    def test_to_utf8(self):
        result = to_utf8(u"admin")
        self.assertEqual(result, b"admin")
        self.assertIsInstance(result, type(b""))

        result = to_utf8(u"öü")
        self.assertEqual(result, u"öü".encode("utf8"))
        self.assertIsInstance(result, type(b""))

        self.assertEqual(to_utf8(b"x"), b"x")

    def test_to_unicode(self):
        result = to_unicode(u"admin")
        self.assertEqual(result, "admin")
        self.assertIsInstance(result, type(u""))

        result = to_unicode(b"admin")
        self.assertEqual(result, "admin")
        self.assertIsInstance(result, type(u""))

    def test_deep_update(self):
        merge = {'first': {'all_rows': {'pass': 'dog', 'number': '1',
                                        "values": {1, 4}}}}
        src = {'first': {'all_rows': {'fail': 'cat', 'number': '5',
                                      "values": {1, 2, 3}}}}
        cmp_ = {'first': {'all_rows':
                          {'pass': 'dog', 'fail': 'cat', 'number': '5',
                           "values": {1, 2, 3, 4}}}}
        result = deep_update(merge, src)
        self.assertEqual(cmp_, result)

    def test_pyeval(self):
        self.assertEqual(pyeval("5"), 5)
        self.assertEqual(pyeval("5+x"), "5+x")
        self.assertEqual(pyeval("5+6"), 11)

    def test_string_to_obj(self):
        obj = string_to_obj("larch.lib.gevent:_DebounceContext")
        self.assertEqual(obj, _DebounceContext)
        self.assertEqual(string_to_obj(obj), _DebounceContext)

        f = string_to_obj("larch.lib.gevent:_DebounceContext.cancel")
        self.assertEqual(f, _DebounceContext.cancel)

        f = string_to_obj(f"{__file__}:UtilsTest")
        self.assertEqual(f.__name__, UtilsTest.__name__)

        f = string_to_obj("lambda x=1: x")
        self.assertEqual(f(), 1)

        logstream.seek(0)
        logstream.truncate(0)
        self.assertRaises(ValueError, string_to_obj, "raise ValueError()")
        self.assertIn("error converting string to obj", logstream.getvalue())

    def test_try_until_timeout(self):
        utils.DEFAULT_TIMEOUT = 1
        os.environ["TIMEOUT"] = "wrong"
        for i in try_until_timeout():
            if i > 5:
                break

        for i in try_until_timeout(0.1):
            pass

        self.assertGreaterEqual(i, 4)

    def test_performance_history(self):
        ph = PerformanceHistory("/", 5)
        for i in range(10):
            ph.record()
        self.assertEqual(len(ph.window), 5)

    def test_yaml_patch(self):
        data = {
            "a": 1,
            "b": "Multi\nLine\nString"}
        cmp_str = """a: 1
b: |-
  Multi
  Line
  String
"""
        result = yaml.dump(data)
        self.assertEqual(result, cmp_str)
        d = yaml.full_load(result)
        self.assertEqual(d, data)

    def test_pidexists(self):
        self.assertTrue(pid_exists(os.getpid()))
        self.assertFalse(pid_exists(0xffff))
        self.assertFalse(pid_exists(-1))


logstream = io.StringIO()


if __name__ == "__main__":
    log_format = ("%(created)f %(levelname)s"
                  " %(pathname)s(%(lineno)d): %(message)s")
    logging.basicConfig(level=logging.DEBUG, format=log_format, stream=logstream)
    unittest.main(failfast=True)
