import io
import traceback
from time import time
from logging import getLogger, Logger
from contextlib import contextmanager
from collections import OrderedDict, deque
from functools import wraps
from itertools import tee
from types import MethodType, FunctionType
from gevent import spawn_later, getcurrent, get_hub, kill
from gevent.event import Event
from gevent.lock import RLock
from gevent.hub import Hub

logger = getLogger('larch.lib')
del getLogger


NO_MAX_WAIT = 9999999


class _DebounceContext:
    # see debounce function in lodash

    def __init__(self, function, wait, leading, max_wait, trailing):
        self.function = function
        self.wait = wait
        self.leading = leading
        self.max_wait = max(max_wait, wait)
        self.trailing = trailing

        try:
            self._spawn_later = function.__self__.spawn_later
        except AttributeError:
            self._spawn_later = spawn_later

        self._last_call_time = self._last_invoke_time = 0
        self._result = self._greenlet = None

    def __repr__(self):
        return f"<{self.__class__.__name__} for {self.function}>"

    def __reduce_ex__(self, protocol):
        raise ValueError("Cannot pickle _DebounceContext")

    def _invoke_func(self, time_):
        args, kwargs = self._last_args
        self._last_args = None
        self._last_invoke_time = time_
        self._result = self.function(*args, **kwargs)
        return self._result

    def _should_invoke(self, time_):
        time_since_last_call = time_ - self._last_call_time
        time_since_last_invoke = time_ - self._last_invoke_time
        return (time_since_last_call >= self.wait
                or time_since_last_invoke >= self.max_wait)

    def _leading_edge(self, time_):
        self._last_invoke_time = time_
        self._greenlet = self._spawn_later(self.wait, self._timer_expired)
        return self._invoke_func(time_) if self.leading else self._result

    def _remaining_wait(self, time_):
        time_since_last_call = time_ - self._last_call_time
        time_since_last_invoke = time_ - self._last_invoke_time
        return min(self.wait-time_since_last_call,
                   self.max_wait-time_since_last_invoke)

    def _timer_expired(self):
        # we are done and ready for the next call, (bool(self._greenlet) must
        # be False even if self.function takes a long time)
        self._greenlet = None
        now = time()
        if self._should_invoke(now):
            return self._trailing_edge(now)

        new_wait = self._remaining_wait(now)
        if new_wait > 0:
            self._greenlet = self._spawn_later(new_wait, self._timer_expired)

    def _trailing_edge(self, time_):
        if self.trailing and self._last_args is not None:
            return self._invoke_func(time_)
        self._last_args = None
        return self._result

    def cancel(self):
        if self._greenlet:
            self._greenlet.kill()
            self._greenlet = None
        self._last_invoke_time = self._last_call_time = 0
        self._last_args = None

    def flush(self):
        return self._trailing_edge(time()) if self._greenlet else self._result

    def __call__(self, *args, **kwargs):
        now = time()
        is_invoking = self._should_invoke(now)

        self._last_args = (args, kwargs)
        self._last_call_time = now

        if is_invoking:
            if not self._greenlet:
                return self._leading_edge(self._last_call_time)

        if not self._greenlet:
            self._greenlet = self._spawn_later(self.wait, self._timer_expired)

        return self._result


class _DebounceDescriptor:
    def __init__(self, func, *args):
        self.func = func
        self.name = f"__{func.__name__}_debounce"
        self.args = args

    def __get__(self, holder, owner):
        if holder is None:
            return self.func

        try:
            return getattr(holder, self.name).func
        except AttributeError:
            bound = MethodType(self.func, holder)
            ctx = _DebounceContext(bound, *self.args)

            @wraps(self.func)
            def bound_wrapper(self, *args, **kwargs):
                return ctx(*args, **kwargs)

            bound_wrapper.ctx = ctx
            bound_wrapper.flush = ctx.flush
            bound_wrapper.cancel = ctx.cancel
            bound_wrapper = MethodType(bound_wrapper, holder)
            ctx.func = bound_wrapper
            setattr(holder, self.name, ctx)
            return bound_wrapper


def debounce(wait, leading=False, max_wait=NO_MAX_WAIT, trailing=True):
    """
    Decorator that will debounce a functions execution (like _.debounce)
    Args:
        wait (float):
            The number of seconds to delay

        leading (bool):
            Specify invoking on the leading edge of the timeout.
            (default False)

        max_wait (float):
            The maximum time func is allowed to be delayed before it's invoked.

        trailing (bool):
            Specify invoking on the trailing edge of the timeout.
            (default True)
    """
    def debounce(f):
        if f.__code__.co_varnames[:1] == ("self",) and isinstance(f, FunctionType):
            return _DebounceDescriptor(f, wait, leading, max_wait, trailing)
        ctx = _DebounceContext(f, wait, leading, max_wait, trailing)
        return wraps(f)(ctx)
    return debounce


def throttle(wait, leading=True, trailing=True):
    return debounce(wait, leading, wait, trailing)


def gevent_tee(iterable, n=2):
    """a gevent save tee"""
    def secure(iterable):
        try:
            while True:
                with lock:
                    value = next(iterable)
                yield value
        except StopIteration:
            pass

    lock = RLock()
    return tuple(secure(i) for i in tee(iterable, n))


class Queue:
    """simple queue"""

    def __init__(self, maxlen):
        self.data = deque()
        self.maxlen = maxlen
        self.can_put = Event()
        self.can_get = Event()

    def __repr__(self):
        return f"{self.__class__.__name__}-{list(self.data)}"

    def __len__(self):
        return len(self.data)

    def __iter__(self):
        get = self.get
        while True:
            r = get()
            if r is StopIteration:
                break
            yield r

    def put(self, obj):
        while self.full():
            self.can_put.clear()
            self.can_put.wait()

        self.data.append(obj)
        self.can_get.set()

    def get(self):
        self._wait_get()
        result = self.data.popleft()
        self.can_put.set()
        return result

    def full(self):
        return len(self.data) >= self.maxlen

    def empty(self):
        return not self.data

    def clear(self):
        self.data.clear()
        self.can_get.clear()
        self.can_put.set()

    def get_all(self):
        self._wait_get()
        r = self.data
        self.data = deque()
        return r

    def _wait_get(self):
        while not self.data:
            self.can_get.clear()
            self.can_get.wait()


class DictQueue(OrderedDict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.can_read = Event()

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self.can_read.set()

    def setdefault(self, key, default=None):
        result = super().setdefault(key, default)
        self.can_read.set()
        return result

    def __delitem__(self, key):
        self._check(super().__delitem__(key))

    def pop(self, *args, **kwargs):
        return self._check(super().pop(*args, **kwargs))

    def popitem(self, last=True):
        return self._check(super().popitem(last))

    def _check(self, result):
        if not self:
            self.can_read.clear()
        return result

    def next(self):
        self.can_read.wait()
        return self.popitem(False)


class _LockType:
    __slots__ = ("cause", "count")

    def __init__(self, cause):
        self.cause = cause
        self.count = 0

    def inc(self):
        self.count += 1

    def dec(self):
        self.count -= 1
        return self.count == 0

    def __repr__(self):
        return "<{}({})>".format(self.cause, self.count)


class MultiLock:
    """
    A lock for multiple objects:

    Example:

    lock = MultiLock()

    Greenlet A:
    with lock("A", 1, 2, 3):
        ...
        a concurrent greenlet B calls:
        with lock("B", 1):
            B blocks because 1 is already locked for A

        a concurrent greenlet C calls
        with lock("C", 4):
            C does not lock because 4 was not locked before
    """

    def __init__(self):
        self.event = Event()
        self.locks = {}

    @contextmanager
    def __call__(self, cause, *ids, **kwds):
        self.acquire(cause, *ids, **kwds)
        try:
            yield 1
        finally:
            self.release(*ids)

    def __contains__(self, id_):
        return id_ in self.locks

    def acquire(self, cause, *ids):
        locks = self.locks
        while True:
            id_locks = (locks.get(id_) for id_ in ids)
            id_locks = (i for i in id_locks if i is not None)
            can_lock = all(i.cause == cause for i in id_locks)
            if can_lock:
                for id_ in ids:
                    locks.setdefault(id_, _LockType(cause)).inc()
                break
            try:
                self.event.wait()  # pragma: no cover  (bug of coverage)
            except BaseException as e:
                logger.debug("cancel lock acquire %r %r\n%r\n%r",
                             cause, e, ids, locks)
                raise

    def release(self, *ids):
        locks = self.locks
        for id_ in ids:
            try:
                lock = locks[id_]
                if lock.dec():
                    del locks[id_]
            except KeyError:  # pragma: no cover
                pass

        self.event.set()
        self.event.clear()


try:
    import larch.reactive as ra

    class PointerEvent(ra.Reactive):
        """A gevent Event that pulses if a reactive.Pointer value changes"""

        def __init__(self, pointer):
            self.value = pointer()
            self.pointer = pointer
            self.event = Event()

        @ra.rule
        def _rule_watch_proxy(self):
            new_value = self.pointer()
            if new_value == self.value:
                return

            self.value = new_value
            yield
            self.event.set()
            self.event.clear()

        def wait(self, timeout=None):
            self.event.wait(timeout)
            return self.value
except ImportError:  # pragma: no cover
    pass


# patch hub for logging unexpected errors
def print_exception(self, context, type_, value, tb):
    if value is not None:
        if isinstance(value, KeyError):  # pragma: no cover
            logger.info("greenlet key error %r\n%r", value, context, exc_info=True)
        else:
            logger.exception("Unexpected error %r\n%r", value, context)
    else:  # pragma: no cover
        logger.error("Unexpected error %r", type_, stack_info=True)


def handle_system_error(self, type, value, *args):  # pragma: no cover
    if type is KeyboardInterrupt:
        if getcurrent() is not get_hub().parent:
            logger.error("send KeyboardInterrupt to main greenlet")
            kill(get_hub().parent, KeyboardInterrupt)

    old_handle_system_error(self, type, value)


def handle_error(context, type_, value, tb):  # pragma: no cover
    logger.exception("Unexpected error %r\n%r", value, context)


Hub.error_handler = handle_error
old_handle_system_error = Hub.handle_system_error
Hub.handle_system_error = handle_system_error
Hub.print_exception = print_exception


# patch Logger for also logging the spawning stack

def findCaller(self, stack_info=False, stacklevel=1):
    result = self.org_findCaller(stack_info, stacklevel)
    if stack_info:
        fn, lno, func, sinfo = result
        greenlet = getcurrent()
        try:
            stack = greenlet.spawning_stack
        except AttributeError:
            return result

        if stack:
            parent = (greenlet.spawning_greenlet()
                      if greenlet.spawning_greenlet else None)

            sio = io.StringIO()
            sio.write(f'\nSpawning Greenlet ({parent}):\n')
            traceback.print_stack(stack, file=sio)
            sinfo += sio.getvalue().rstrip()
            sio.close()
            result = fn, lno, func, sinfo

    return result


if Logger.findCaller.__code__.co_argcount == 2:  # pragma: no cover
    # < python 3.8
    def findCaller33(self, stack_info=False, stacklevel=1):
        return self.org_org_findCaller(stack_info)
    Logger.org_findCaller = findCaller33
    Logger.org_org_findCaller = Logger.findCaller
else:
    Logger.org_findCaller = Logger.findCaller

Logger.findCaller = findCaller
