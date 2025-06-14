import unittest
import larch.lib.aspect as lra
import gc

vars_ = None


@lra.pointcut
class StoragePointCut(object):
    sensless = None

    def put_start(self):
        pass

    def put_end(self, context):
        pass

    def get_start(self, context):
        pass

    def get_end(self, context):
        pass

    def change_value(self):
        pass


@lra.pointcut
class SubStoragePointCut(StoragePointCut):
    def finished(self, context):
        pass


class LoggingMixin(object):
    def put_start(self):
        vars_.self.put_calls.append("logging start")

    def put_end(self, context):
        context["self"].put_calls.append("logging end")


class Logging(LoggingMixin, lra.aspect(StoragePointCut)):
    def __init__(self, pointcut=None):
        super(Logging, self).__init__(pointcut)


class SubLogging(LoggingMixin, lra.aspect(SubStoragePointCut)):
    def finished(self, context):
        context["self"].finish_calls.append("logging finished")


class FallBack1(lra.aspect(StoragePointCut)):
    def put_start(self):
        vars_.self.put_calls.append("fall back1 start")
        return 1

    def put_end(self, context):
        context["self"].put_calls.append("fall back1 end")

    @lra.order(2)
    def get_start(self, context):
        context["self"].get_calls.append("fall back1 start")
        return 1

    def get_end(self, context):
        context["self"].get_calls.append("fall back1 end")


class FallBack2(lra.aspect(StoragePointCut)):
    def put_start(self):
        vars_.self.put_calls.append("fall back2 start")
        return 2

    def put_end(self, context):
        context["self"].put_calls.append("fall back2 end")

    def get_start(self, context):
        context["self"].get_calls.append("fall back2 start")
        return 2


class MakeException(lra.aspect(StoragePointCut)):
    def put_start(self):
        raise RuntimeError()


class ChangeValue(lra.aspect(StoragePointCut)):
    def change_value(self):
        vars_.value = 20
        try:
            vars_.not_there
        except AttributeError:
            pass


class Storage(object):
    def __init__(self):
        self.pointcut = StoragePointCut()
        self.put_calls = []
        self.get_calls = []

    def put(self):
        result = self.pointcut.put_start()
        self.put_calls.append("middle %s" % result)
        self.pointcut.put_end(vars())

    def get(self):
        result = self.pointcut.get_start(vars())
        self.get_calls.append("middle %s" % result)
        self.pointcut.get_end(vars())

    def change_internal_var(self):
        value = 10
        self.pointcut.change_value()
        self.value = value


class SubStorage(Storage):
    def __init__(self):
        super(SubStorage, self).__init__()
        self.pointcut = SubStoragePointCut()
        self.finish_calls = []

    def finished(self):
        self.pointcut.finished(vars())


class AspectTest(unittest.TestCase):
    def test_no_aspect(self):
        s = Storage()
        s.get()
        s.put()

        self.assertEqual(s.put_calls, ['middle None'])
        self.assertEqual(s.get_calls, ['middle None'])

    def test_one_aspect(self):
        s = Storage()
        l = Logging(s.pointcut)

        self.assertEqual(len(l.pointcut), 1)
        l.add_pointcut(s.pointcut)  # do not add again
        self.assertEqual(len(l.pointcut), 1)

        # from pudb import set_trace; set_trace()
        s.get()
        s.put()

        self.assertEqual(s.put_calls,
                         ['logging start', 'middle None', 'logging end'])
        self.assertEqual(s.get_calls, ['middle None'])

        del l
        s.put_calls = []
        s.put()
        self.assertEqual(s.get_calls, ['middle None'])

    def test_remove(self):
        s = Storage()
        log = Logging(s.pointcut)

        # from pudb import set_trace; set_trace()
        s.get()
        s.put()

        self.assertEqual(s.put_calls,
                         ['logging start', 'middle None', 'logging end'])
        self.assertEqual(s.get_calls, ['middle None'])

        log.clear_pointcut()
        s.put_calls = []
        s.put()
        self.assertEqual(s.get_calls, ['middle None'])

    def test_return(self):
        s = Storage()
        log = Logging(s.pointcut)
        f1 = FallBack1(pointcut=s.pointcut)
        f2 = FallBack2(s)

        s.get()
        s.put()

        self.assertEqual(s.get_calls,
                         ['fall back2 start', 'middle 2', 'fall back1 end'])
        self.assertEqual(s.put_calls,
                         ['logging start', 'fall back1 start', 'middle 1',
                          'logging end', 'fall back1 end', 'fall back2 end'])

        del f1
        del f2
        del log

    def test_exception(self):
        s = Storage()
        log = Logging()
        log.add_pointcut(s.pointcut)
        # from pudb import set_trace; set_trace()
        e = MakeException(s.pointcut)
        f1 = FallBack1(s)

        self.assertRaises(RuntimeError, s.put)
        self.assertEqual(s.put_calls, ['logging start'])

        del e
        gc.collect()

        s.put_calls = []
        s.put()

        self.assertEqual(s.put_calls, ['logging start', 'fall back1 start',
                                       'middle 1', 'logging end',
                                       'fall back1 end'])
        del f1

    def test_assign1(self):
        self.assertRaises(ValueError, Logging, 1)

    def test_assign2(self):
        s = Storage()
        log = Logging(s)
        self.assertEqual(log.pointcut, [s.pointcut])

    def test_subclassing1(self):
        s = SubStorage()
        log = SubLogging(s.pointcut)

        # from pudb import set_trace; set_trace()
        s.get()
        s.put()
        s.finished()

        self.assertEqual(s.put_calls,
                         ['logging start', 'middle None', 'logging end'])
        self.assertEqual(s.get_calls, ['middle None'])
        del log

    def test_subclassing2(self):
        s = SubStorage()
        log = SubLogging(s.pointcut)

        s.get()
        s.put()
        s.finished()

        self.assertEqual(s.put_calls,
                         ['logging start', 'middle None', 'logging end'])
        self.assertEqual(s.get_calls, ['middle None'])
        self.assertEqual(s.finish_calls, ['logging finished'])
        del log

    def test_change_var(self):
        s = Storage()
        log = ChangeValue(s.pointcut)
        s.change_internal_var()
        self.assertEqual(s.value, 20)
        del log


if __name__ == "__main__":
    unittest.main()
