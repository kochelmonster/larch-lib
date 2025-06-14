# -*- coding: utf-8 -*-
"""
Tests the serval modules in larch.db.kernel
"""
import logging
import io
import unittest
from larch.lib.cache import LIRSCache, LRUCache


class LIRSTest(unittest.TestCase):
    def create_cache(self):
        cache = LIRSCache(3, 2)
        cache[8] = True
        cache[4] = True
        cache[1] = True
        cache[8] = True
        cache[4] = True
        cache[9] = True
        cache[6] = True
        cache[1] = True
        cache[2] = True
        cache[3] = True
        cache[5] = True
        return cache

    def test_cache_hit(self):
        cache = self.create_cache()

        items = set(cache)
        self.assertEqual(items, set([1, 3, 4, 5, 8]))
        self.assertEqual(len(cache), 5)
        self.assertEqual(
            list(cache._stack.s.items()),
            [(8, 0), (4, 0), (9, 1), (6, 1), (1, 0), (2, 1), (3, 1), (5, 1)])
        self.assertEqual(list(cache._stack.q.items()),
                         [(3, True), (5, True)])

        cache[4]
        self.assertEqual(
            list(cache._stack.s.items()),
            [(8, 0), (9, 1), (6, 1), (1, 0), (2, 1), (3, 1), (5, 1), (4, 0)])
        self.assertEqual(list(cache._stack.q.items()),
                         [(3, True), (5, True)])

        cache[8]
        self.assertEqual(
            list(cache._stack.s.items()),
            [(1, 0), (2, 1), (3, 1), (5, 1), (4, 0), (8, 0)])
        self.assertEqual(list(cache._stack.q.items()),
                         [(3, True), (5, True)])

        cache[3]
        self.assertEqual(
            list(cache._stack.s.items()),
            [(4, 0), (8, 0), (3, 0)])
        self.assertEqual(list(cache._stack.q.items()),
                         [(5, True), (1, True)])

        cache[5]
        self.assertEqual(
            list(cache._stack.s.items()),
            [(4, 0), (8, 0), (3, 0), (5, 1)])
        self.assertEqual(list(cache._stack.q.items()),
                         [(1, True), (5, True)])

        self.assertTrue(1 in cache)
        self.assertFalse(7 in cache)
        cache[7] = True
        self.assertEqual(
            list(cache._stack.s.items()),
            [(4, 0), (8, 0), (3, 0), (5, 1), (7, 1)])
        self.assertEqual(list(cache._stack.q.items()),
                         [(5, True), (7, True)])
        self.assertFalse(1 in cache)

        self.assertTrue(5 in cache)
        self.assertEqual(cache.get(9), None)
        cache[9] = True
        self.assertEqual(
            list(cache._stack.s.items()),
            [(4, 0), (8, 0), (3, 0), (5, 1), (7, 1), (9, 1)])
        self.assertEqual(list(cache._stack.q.items()),
                         [(7, True), (9, True)])
        self.assertFalse(5 in cache)

        self.assertTrue(7 in cache)
        cache[5] = True
        self.assertEqual(
            list(cache._stack.s.items()),
            [(8, 0), (3, 0), (7, 1), (9, 1), (5, 0)])
        self.assertEqual(list(cache._stack.q.items()),
                         [(9, True), (4, True)])
        self.assertFalse(7 in cache)

        self.assertEqual(cache.get("notthere"), None)
        self.assertEqual(cache.get(8), True)

    def test_cache_del(self):
        cache = self.create_cache()
        self.assertEqual(cache.next_to_evict(), 3)
        self.assertEqual(cache.pop("not existend"), None)

        del cache[8]
        self.assertEqual(
            list(cache._stack.s.items()),
            [(4, 0), (9, 1), (6, 1), (1, 0), (2, 1), (3, 0), (5, 1)])
        self.assertEqual(list(cache._stack.q.items()),
                         [(5, True)])

        del cache[4]
        self.assertEqual(
            list(cache._stack.s.items()),
            [(1, 0), (2, 1), (3, 0), (5, 0)])
        self.assertEqual(list(cache._stack.q.items()), [])

        del cache[3]
        self.assertEqual(
            list(cache._stack.s.items()),
            [(1, 0), (5, 0)])
        self.assertEqual(list(cache._stack.q.items()), [])

        cache = self.create_cache()
        del cache[3]
        self.assertEqual(
            list(cache._stack.s.items()),
            [(8, 0), (4, 0), (9, 1), (6, 1), (1, 0), (2, 1), (5, 1)])
        self.assertEqual(list(cache._stack.q.items()),
                         [(5, True)])

        self.assertEqual(len(cache), 4)
        cache.clear()
        self.assertEqual(len(cache), 0)

    def test_stack_evict(self):
        stack = self.create_cache()._stack

        self.assertEqual(stack.next_to_evict(), 3)

        evicted = [s for i, s in zip(range(3), stack.evict())]
        self.assertEqual(evicted, [3, 5, 8])
        self.assertEqual(
            list(stack.s.items()),
            [(4, 0), (9, 1), (6, 1), (1, 0), (2, 1)])
        self.assertEqual(list(stack.q.items()), [])
        self.assertEqual(stack.next_to_evict(), 4)

        evicted = [s for i, s in zip(range(1), stack.evict())]
        self.assertEqual(evicted, [4])
        self.assertEqual(
            list(stack.s.items()),
            [(1, 0), (2, 1)])
        self.assertEqual(list(stack.q.items()), [])

        all_done = list(stack.evict())
        self.assertEqual(all_done, [1])
        self.assertEqual(len(stack.q), 0)
        self.assertEqual(len(stack.s), 0)

        nothing = list(stack.evict())
        self.assertEqual(nothing, [])
        self.assertRaises(ValueError, stack.next_to_evict)


class TestLRUCache(unittest.TestCase):
    def test_cache(self):
        tst = LRUCache(10, 10)
        for i in range(10):
            tst[i] = i

        self.assertEqual(tst.size, 10)
        self.assertEqual(len(tst), 10)

        tst[1] = 100
        self.assertEqual(tst.size, 10)
        self.assertEqual(len(tst), 10)

        tst[10] = 10
        self.assertEqual(tst.size, 10)
        self.assertEqual(len(tst), 10)
        self.assertEqual(list(tst), [2, 3, 4, 5, 6, 7, 8, 9, 1, 10])

        self.assertEqual(tst[10], 10)

        del tst[2]
        self.assertEqual(tst.size, 9)
        self.assertEqual(len(tst), 9)
        self.assertEqual(list(tst.values()), [3, 4, 5, 6, 7, 8, 9, 100, 10])

        tst.clear()
        self.assertEqual(tst.size, 0)
        self.assertEqual(len(tst), 0)


logstream = io.StringIO()

if __name__ == "__main__":
    log_format = ("%(created)f %(levelname)s"
                  " %(pathname)s(%(lineno)d): %(message)s")
    logging.basicConfig(level=logging.ERROR, format=log_format,
                        stream=logstream)
    unittest.main(failfast=True)
