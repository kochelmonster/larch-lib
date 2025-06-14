import os
import sys
import logging
from collections import deque
from importlib import import_module
from time import time
from runpy import run_path
try:
    from gevent import sleep
except ImportError:  # pragma: no cover
    from time import sleep
try:
    import psutil
except ImportError:  # pragma: no cover
    # performance counter does not work
    pass

logger = logging.getLogger("larch.lib")


def pyeval(val):
    """if val contains a python expression it is evaluated."""
    try:
        return eval(val) if isinstance(val, str) else val
    except Exception:
        return val


def string_to_obj(obj):
    if isinstance(obj, str):
        try:
            module, el = obj.rsplit(":", 1)
            path = el.split(".")
            try:
                obj = import_module(module)
            except ModuleNotFoundError:
                try:
                    obj = run_path(module)
                except OSError:
                    return eval(obj)

                obj = obj[path[0]]
                path = path[1:]

            for part in path:
                obj = getattr(obj, part)
        except Exception as e:  # pragma: no cover
            logger.debug("error converting string to obj %r: %r", obj, e, exc_info=True)
            raise

        return obj

    return obj


def deep_update(merged, source):
    """
    >>> a = {'first': {'all_rows': {'pass': 'dog', 'number': '1' }}}
    >>> b = {'first': {'all_rows': {'fail': 'cat', 'number': '5' }}}
    >>> deep_update(a, b) ==
            {'first': {'all_rows':
                        {'pass': 'dog', 'fail': 'cat', 'number': '5'}}}
    True
    """
    for key, value in source.items():
        if isinstance(value, dict):
            # get node or create one
            node = merged.setdefault(key, {})
            deep_update(node, value)
        elif isinstance(value, set):
            dest = merged.get(key, set())
            if isinstance(dest, set):
                value = value | dest
            merged[key] = value
        else:
            merged[key] = value

    return merged


DEFAULT_TIMEOUT = 10


def get_default_timeout():
    try:
        return float(os.environ.get("TIMEOUT", DEFAULT_TIMEOUT))
    except Exception:
        pass
    return DEFAULT_TIMEOUT


def try_until_timeout(timeout=None, delta=0.1):
    """iterates until fail_timeout exceeds or the condition loop breaks"""
    i = 1
    yield i  # there is always one attempt

    if timeout is None:
        timeout = get_default_timeout()

    if delta >= timeout:
        delta = timeout / 5

    start = time()
    sleep(delta)
    while time() - start < timeout:
        i += 1
        yield i
        sleep(delta)


def to_utf8(x):
    if not isinstance(x, bytes):
        return x.encode("utf8")
    return x


def to_unicode(x):
    if isinstance(x, bytes):
        return x.decode("utf8", "ignore")
    return str(x)


to_str = to_unicode


class PerformanceHistory:
    def __init__(self, partition, size=24):
        self.size = size
        self.window = deque()
        self.partition = partition
        self.process = psutil.Process()
        self.record()

    def read(self):
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(self.partition)
        network = psutil.net_io_counters()
        cpu_count = psutil.cpu_count()
        p_cpu = self.process.cpu_percent()
        p_mem = self.process.memory_info()
        item = {
            "cpu": tuple(c/cpu_count for c in psutil.getloadavg()) + (p_cpu,),
            "memory": (mem.total, mem.used, mem.available) + p_mem,
            "disk": (disk.total, disk.used, disk.free),
            "network": (network.bytes_sent, network.bytes_recv),
            "time": time()
        }
        try:
            item["temp"] = {
                f"{k}.{t.label or i}": (t.current, t.high)
                for k, v in psutil.sensors_temperatures().items() for i, t in enumerate(v)}
        except AttributeError:  # pragma: no cover
            pass  # windows
        return item

    def record(self):
        self.window.append(self.read())
        if len(self.window) > self.size:
            self.window.popleft()


def str_presenter(dumper, data):
    args = {}
    if "\n" in data:
        args["style"] = "|"
    return dumper.represent_scalar('tag:yaml.org,2002:str', data, **args)


try:
    import yaml
    yaml.add_representer(str, str_presenter)
except ImportError:  # pragma: no cover
    pass


if sys.platform == "win32":  # pragma: no cover
    import ctypes.wintypes
    _STILL_ACTIVE = 259

    def pid_exists(pid):
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(1, 0, pid)
        if handle == 0:
            return False

        # If the process exited recently, a pid may still exist for the handle.
        # So, check if we can get the exit code.
        exit_code = ctypes.wintypes.DWORD()
        is_running = (
            kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) == 0)
        kernel32.CloseHandle(handle)
        return is_running or exit_code.value == _STILL_ACTIVE
else:
    import errno

    def pid_exists(pid):
        """Check whether pid exists in the current process table."""
        if pid < 0:
            return False
        try:
            os.kill(pid, 0)
        except OSError as e:
            return e.errno == errno.EPERM

        if sys.platform.startswith("linux"):
            try:
                with open(f"/proc/{pid}/status", "r"):
                    pass
            except FileNotFoundError:  # pragma: no cover
                return False

        return True
