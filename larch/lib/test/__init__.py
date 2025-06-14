import os
import logging
from pathlib import Path
from ..logging import PPFormater
from ..utils import try_until_timeout


try:
    logging.Logger.makeRecord.udn_record
except AttributeError:
    # patch logger
    def makeRecord(self, *args, **kwargs):
        record = old_make_record(self, *args, **kwargs)
        record.udn = os.environ.get("LARCH_UDN", "main")
        return record

    makeRecord.udn_record = True
    old_make_record = logging.Logger.makeRecord
    logging.Logger.makeRecord = makeRecord


def config_logging(log_file=None, module_file_name="", level=logging.DEBUG, filemode="w"):
    # clear all handlers that any library (wsgidav) illegaly registered
    # in module code. And let bascConfig work again.
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)

    if log_file:
        log_file = Path(log_file)
        if module_file_name:
            module_file_name = Path(module_file_name).resolve()
            if not module_file_name.is_dir():
                module_file_name = module_file_name.parent

            log_file = module_file_name/log_file
            os.makedirs(log_file.parent, exist_ok=True)

        if "LARCH_START" not in os.environ and not os.environ.get('WERKZEUG_RUN_MAIN'):
            try:
                os.unlink(log_file)
            except OSError:
                pass
        os.makedirs(log_file.parent, exist_ok=True)

    # the starting ">" is a helper for regex parsing log messages
    log_format = ("> %(udn)s %(created)f %(levelname)s %(name)s"
                  " %(pathname)s(%(lineno)d): %(message)s")
    logging.basicConfig(level=level, format=log_format, filename=log_file, filemode=filemode)
    logging.captureWarnings(True)
    logging.getLogger('larch.upnp.hub.wsgi').setLevel(logging.ERROR)
    logging.getLogger('larch.upnp.device').setLevel(logging.ERROR)
    logging.getLogger("py.warnings").setLevel(level)

    for h in root.handlers:
        h.setFormatter(PPFormater(log_format))

    return log_file


def iter_expect(timeout=20, sleep_time=0.5):
    """
    use it like this:

    for i in iter_expect():
        with i:
            self.assertEqual(selecion_el.get_attribute("text"), "test")

    will try the line until no exception is thrown or until timeout is
    reached.
    """
    class NoExceptionContext:
        exception = RuntimeError()

        def __bool__(self):
            return False

        def __enter__(self):
            pass

        def __exit__(self, type, value, traceback):
            if "Timeout" in repr(value):
                return False
            self.exception = value
            return True

    class ExceptionContext:
        def __bool__(self):
            return True

        def __enter__(self):
            pass

        def __exit__(self, type, value, traceback):
            return False

    context = NoExceptionContext()
    for i in try_until_timeout(timeout, sleep_time):
        yield context
        if context.exception is None:
            return

    yield ExceptionContext()
