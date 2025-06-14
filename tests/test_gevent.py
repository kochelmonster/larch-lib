# -*- coding: utf-8 -*-
"""
Tests the serval modules in larch.db.kernel
"""
import logging
import io
import unittest
import gevent
import gevent.local
from pickle import dumps
from itertools import permutations
from larch.lib.gevent import MultiLock, debounce, throttle, DictQueue, Queue, gevent_tee


logger = logging.getLogger("test")


class TestLock(unittest.TestCase):
    def test_lock(self):
        """tests locking in different situations (needs long time)"""
        lock = MultiLock()
        order = []

        def log(message, name, cause):
            # print "log", message, name, cause
            order.append((name, message))

        def g(name, cause, *keys):
            # log("before lock", name, cause)
            with lock(cause, *keys):
                self.assertIn(keys[0], lock)
                log("lock", name, cause)
                gevent.sleep(0.05)
                log("end lock", name, cause)

            # log("after lock", name, cause)

        def assertLockConcurrently(name1, name2):
            index1 = order.index((name1, "lock"))
            index2 = order.index((name2, "lock"))
            delta = abs(index1-index2)
            self.assertEqual(delta, 1)

        def assertLockSeparated(name1, name2):
            index1 = order.index((name1, "lock"))
            index2 = order.index((name2, "lock"))
            delta = abs(index1-index2)
            self.assertGreater(delta, 1)

        calls = [
            (g, "1", "c1", "a", "b"),
            (g, "2", "c2", "b", "c"),
            (g, "3", "c3", "c", "d"),
            (g, "4", "c4", "a", "b", "c", "d"),
            (g, "5", "c4", "a", "b", "c", "d")]

        for i, clls in enumerate(permutations(calls)):
            # print "test", i
            del order[:]
            greenlets = [gevent.spawn(*args) for args in clls]
            gevent.joinall(greenlets)
            assertLockConcurrently("1", "3")
            assertLockConcurrently("4", "5")
            assertLockSeparated("4", "2")
            assertLockSeparated("1", "2")
            self.assertFalse(lock.locks)

    def test_lock_timeout(self):
        lock = MultiLock()
        lock.acquire("test", 1)
        with gevent.Timeout(0.1):
            try:
                lock.acquire("test1", 1)
            except gevent.Timeout:
                pass
            else:
                self.assertFalse(True)


class DebounceObj:
    spawn_later = gevent.spawn_later

    def __init__(self):
        self.collect = []

    @debounce(0.2)
    def call1(self, arg):
        """a debounce test"""
        self.collect.append(arg)
        return arg

    @debounce(0.2, True)
    def call2(self, arg):
        self.collect.append(arg)
        return arg

    @debounce(0.3, max_wait=0.4)
    def call3(self, arg):
        self.collect.append(arg)
        return arg


class TestDebounce(unittest.TestCase):
    def test_throttle(self):
        collected = []

        @throttle(0.1)
        def collect(value):
            if value == 10:
                raise ValueError("test")  # must be logged
            collected.append(value)

        for i in range(10):
            collect(i)

        gevent.sleep(0.2)
        self.assertEqual(collected, [0, 9])
        gevent.sleep(0.2)

        del collected[:]

        logstream.truncate(0)
        self.assertRaises(ValueError, collect, 10)
        self.assertEqual(collected, [])

        gevent.sleep(0.2)
        collect(11)
        self.assertEqual(collected, [11])

    def test_debounce(self):
        obj = DebounceObj()
        call1 = obj.call1
        self.assertIsInstance(
            DebounceObj.call1, type(TestDebounce.test_debounce))

        # import pudb; pudb.set_trace()
        self.assertEqual(None, obj.call1(1))
        self.assertEqual(obj.call1.__name__, "call1")
        self.assertEqual(obj.call1.__doc__, "a debounce test")

        self.assertEqual(None, call1(2))  # not obj.call1
        gevent.sleep(0.3)
        self.assertEqual(2, obj.call1(3))
        gevent.sleep(0.3)
        self.assertEqual(obj.collect, [2, 3])

        del obj.collect[:]
        self.assertEqual(3, obj.call1(4))
        obj.call1.cancel()
        self.assertEqual(3, obj.call1(5))
        obj.call1.flush()
        self.assertEqual(obj.collect, [5])

    def test_debounce_leading(self):
        obj = DebounceObj()
        self.assertEqual(1, obj.call2(1))
        self.assertEqual(1, obj.call2(2))
        self.assertEqual(1, obj.call2(3))
        gevent.sleep(0.3)
        self.assertEqual(None, obj.call1(4))
        gevent.sleep(0.3)
        self.assertEqual(obj.collect, [1, 3, 4])

    def test_debounce_maxwait(self):
        obj = DebounceObj()
        self.assertEqual(None, obj.call3(1))
        gevent.sleep(0.25)
        self.assertEqual(None, obj.call3(2))
        gevent.sleep(0.25)
        self.assertEqual(2, obj.call3(3))
        gevent.sleep(0.4)

    def test_no_pickle(self):
        obj = DebounceObj()
        obj.call1()
        obj.call1()
        self.assertRaises(ValueError, dumps, obj)

    def test_throttle_bug(self):
        collected = []

        @throttle(0.2)
        def func(value):
            if value == 2:
                gevent.sleep(0.2)
            collected.append(value)

        logstream.seek(0)
        logstream.truncate(0)

        func(1)
        gevent.sleep(0.18)
        func(2)
        gevent.sleep(0.021)
        func(3)
        gevent.sleep(1)

        self.assertEqual(collected, [1, 2, 3])


class TestQueues(unittest.TestCase):
    def test_dict_queue(self):
        dq = DictQueue()
        dq[2] = 0
        dq[1] = "test"
        dq[0] = 2
        self.assertEqual(dq.pop(1), "test")
        self.assertEqual(dq.next(), (2, 0))
        self.assertEqual(dq.next(), (0, 2))

        with self.assertRaises(gevent.Timeout):
            with gevent.Timeout(0.1):
                dq.next()

        self.assertFalse(dq.can_read.is_set())
        dq.setdefault(0, 1)
        self.assertTrue(dq.can_read.is_set())

    def test_queue(self):
        q = Queue(2)

        q.put(1)
        q.put(2)

        with self.assertRaises(gevent.Timeout):
            with gevent.Timeout(0.1):
                q.put(3)

        self.assertEqual(len(q), 2)
        self.assertEqual(q.get(), 1)
        self.assertEqual(q.get(), 2)

        with self.assertRaises(gevent.Timeout):
            with gevent.Timeout(0.1):
                q.get()

        q.put(3)
        q.put(4)
        self.assertEqual(list(q.get_all()), [3, 4])

        q.put(5)
        q.put(6)
        q.clear()
        self.assertEqual(len(q), 0)
        self.assertTrue(q.can_put.is_set())
        self.assertFalse(q.can_get.is_set())
        self.assertTrue(q.empty())

        def reader(queue, result):
            for i in queue:
                result.append(i)

        result = []
        g = gevent.spawn(reader, q, result)
        q.put(7)
        q.put(8)
        q.put(9)
        q.put(10)
        q.put(StopIteration)

        g.join()
        self.assertEqual(result, [7, 8, 9, 10])


class TestTee(unittest.TestCase):
    def test_tee(self):
        counts = range(20)
        c1, c2, c3 = gevent_tee(counts, 3)

        def collector(input_):
            output = []
            for i in input_:
                gevent.sleep(0)
                output.append(i)
            return output

        g1 = gevent.spawn(collector, c1)
        g2 = gevent.spawn(collector, c2)
        g3 = gevent.spawn(collector, c3)

        cmp_ = list(range(20))
        self.assertEqual(g3.get(), cmp_)
        self.assertEqual(g2.get(), cmp_)
        self.assertEqual(g1.get(), cmp_)


class TestErrors(unittest.TestCase):
    def test_greenlet_error(self):
        def raises_error():
            raise RuntimeError()

        logstream.seek(0)
        logstream.truncate(0)
        gevent.spawn(raises_error)
        gevent.sleep(0.1)

        exception_string = logstream.getvalue()
        self.assertIn("RuntimeError", exception_string)
        self.assertIn("raises_error", exception_string)

    def test_logging(self):
        def log_stack():
            logger.error("greenlet_stack", stack_info=True)

        logstream.seek(0)
        logstream.truncate(0)
        gevent.spawn(log_stack).join()
        logstring = logstream.getvalue()
        self.assertIn("Spawning Greenlet", logstring)
        self.assertIn("test_logging", logstring)

        logstream.seek(0)
        logstream.truncate(0)
        logger.error("no_greenlet_stack", stack_info=True)
        logstring = logstream.getvalue()
        self.assertNotIn("Spawning Greenlet", logstring)


try:
    from larch.reactive import Reactive, Cell, Pointer
    from larch.lib.gevent import PointerEvent

    class Src(Reactive):
        value = Cell()

    class TestPointerEvent(unittest.TestCase):
        def test_event(self):
            src = Src()
            pe = PointerEvent(Pointer(src).value)
            gevent.spawn(setattr, src, "value", 1)
            self.assertEqual(pe.wait(), 1)
except ImportError:
    pass

logstream = io.StringIO()


if __name__ == "__main__":
    log_format = ("%(created)f %(levelname)s %(pathname)s(%(lineno)d): %(message)s")
    logging.basicConfig(level=logging.ERROR, format=log_format, stream=logstream)
    unittest.main(failfast=True)
