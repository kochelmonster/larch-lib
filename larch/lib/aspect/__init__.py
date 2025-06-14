"""Provides an aspect programming functionality"""
import sys
import ctypes
import warnings
from gc import collect
from weakref import ref, WeakSet
from types import MethodType, FunctionType
from bisect import bisect
from functools import total_ordering

__all__ = ("Pointcut", "Aspect", "pointcut", "aspect", "order")


@total_ordering
class _Last:
    def __lt__(self, other):
        return isinstance(other, _Last)


class Pointcut:
    """A base class for pointcuts to enable"""

    def __init__(self):
        self._advices = {}

    def __repr__(self):
        return f"<{self.__class__.__name__}-{len(self._advices)}>"

    def _add_aspect(self, aspect):
        collect()  # avoids garbage collection during bisect
        raspect = ref(aspect, self._remove_aspect_proxy)
        jps = aspect.__joinpoints__ & self.__joinpoints__

        for jp in jps:
            method = getattr(aspect.__class__, jp)
            try:
                if method.__joinpoint__:
                    # not implemented => no advice has to be generated
                    continue
            except AttributeError:
                pass

            method.__globals__["vars_"] = frame_vars
            order = getattr(method, "__advice_order__", 0)
            advices = self._advices.get(jp)
            if advices is not None:
                index = bisect(advices, (order, _Last()))
                advices.insert(index, (order, method, raspect))
            else:
                setattr(self, jp, self._make_advice(order, method, raspect))

    def _remove_aspect(self, aspect):
        self._remove_aspect_proxy(ref(aspect))

    def _remove_aspect_proxy(self, raspect):
        for jp, advices in list(self._advices.items()):
            try:
                index = next(
                    i for i, (_, m, r) in enumerate(advices) if r == raspect)
            except StopIteration:  # pragma: no cover
                continue
            del advices[index]

            if not advices:
                # back to default handler (defined in Pointcut declaration)
                delattr(self, jp)
                del self._advices[jp]

    def _make_advice(self, order, method, raspect):
        advices = [(order, method, raspect)]
        self._advices[method.__name__] = advices

        def call_advice(*args, **kwargs):
            for _, m, r in advices:
                result = m(r(), *args, **kwargs)
                if result is not None:
                    return result

        return call_advice


class Aspect:
    """A base class for Aspects"""

    def __init__(self, pointcut=None, **kwargs):
        super().__init__(**kwargs)
        self._pointcuts = WeakSet()
        if pointcut is not None:
            self.add_pointcut(pointcut)

    @property
    def pointcut(self):
        return list(self._pointcuts)

    def clear_pointcut(self):
        for pc in self._pointcuts:
            pc._remove_aspect(self)
        self._pointcuts.clear()

    def add_pointcut(self, value):
        def try_set_pointcut(value):
            if isinstance(value, self.__pointcuts__):
                for pc in self.__pointcuts__:
                    if type(value) == pc:
                        if value in self._pointcuts:
                            return True
                        self._pointcuts.add(value)
                        value._add_aspect(self)
                        return True

            return False

        if try_set_pointcut(value):
            # value was a valid pointcut
            return self

        # no search for pointcut attributes
        if not any(try_set_pointcut(getattr(value, n)) for n in dir(value)):
            # no point cut attribute
            raise ValueError("No pointcut", value)

        return self


def get_joinpoints(cls):
    """returns all publib methods of a class"""
    def decorate(name, method):
        method.__joinpoint__ = True
        return name

    return frozenset(decorate(name, method)
                     for name, method in cls.__dict__.items()
                     if (isinstance(method, (MethodType, FunctionType))
                         and not name.startswith("_")))


def pointcut(cls):
    """A class decorator making an ordinary class to a pointcut"""
    if not issubclass(cls, Pointcut):
        bases = (Pointcut,) + (cls,)
    else:
        bases = (cls,)

    newcls = type(object)(cls.__name__, bases, dict(cls.__dict__))
    newcls.__joinpoints__ = get_joinpoints(cls) | \
        getattr(cls, "__joinpoints__", frozenset())
    return newcls


def aspect(*pointcuts):
    """create an aspect base class for the given pointcuts."""
    bases = (Aspect,) + pointcuts
    attribs = {
        "__pointcuts__": pointcuts,
        "__joinpoints__": frozenset().union(
            *[p.__joinpoints__ for p in pointcuts])
    }
    name = "".join(sorted(p.__name__ for p in pointcuts))
    return type(name+"Base", bases, attribs)


def order(order):
    """A method decorator setting the call order of an advice."""
    def set_order(method):
        method.__advice_order__ = order
        return method

    return set_order


class FrameVars:
    def __init__(self):
        try:
            self.__dict__.update({
                "to_fast": ctypes.pythonapi.PyFrame_LocalsToFast,
                "py_object": ctypes.py_object,
                "cy_zero": ctypes.c_int(0)})
        except AttributeError:  # pragma: no cover
            warnings.warn("FrameVars will not work")

    def __getattr__(self, name):
        f = sys._getframe(3)
        try:
            return f.f_locals[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        f = sys._getframe(3)
        f.f_locals[name] = value
        self.to_fast(self.py_object(f), self.cy_zero)


frame_vars = FrameVars()
