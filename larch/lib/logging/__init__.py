import re
import logging
from bisect import bisect
from datetime import datetime
from pprint import pformat


WIDTH = 150
MAX_SIZE = 20000


class PFormatPrinter:
    __slots__ = ("obj",)

    def __init__(self, obj):
        self.obj = obj

    def __repr__(self):
        return pformat(self.obj, width=WIDTH)[:MAX_SIZE]


class PExceptionPrinter:
    __slots__ = ("obj",)

    def __init__(self, obj):
        self.obj = obj

    def __repr__(self):
        args = self.obj.args
        if not args:
            return f"{self.obj.__class__.__name__}"

        args = pformat(args, width=WIDTH)
        if args.find("\n") >= 0:
            args = "\n" + args
        else:
            args = " - " + args
        return f"{self.obj.__class__.__name__}{args}"


class PPFormater(logging.Formatter):
    """A formatter pretty printing complex structures"""

    def format(self, record):
        def transform(arg):
            logging_func = getattr(type(arg), "__logging__", None)
            if logging_func:
                arg = logging_func(arg)

            if isinstance(arg, (dict, set, frozenset, list, tuple)):
                return PFormatPrinter(arg)

            if isinstance(arg, Exception):
                return PExceptionPrinter(arg)

            return arg

        if not isinstance(record.args, tuple):
            record.args = [record.args]

        record.args = tuple(transform(a) for a in record.args)
        return super().format(record)


class LogFileParser:
    COLUMNS = re.compile(r"%\((\w+)\)([sdf])")
    LPAREN = re.compile(r"\(")
    RPAREN = re.compile(r"\)")

    DATE_PARSER = r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d[.,]?\d*"
    FLOAT_PARSER = r"\d+[.]\d+"
    INT_PARSER = r"\d+"
    PATH_PARSER = r"[.\w\/:\\ _-]+|\(unknown file\)"
    STRING_PARSER = r"\w+"
    LEVEL_PARSER = r"DEBUG|INFO|WARNING|ERROR|CRITICAL"
    ALL_PARSER = r".+"
    NAME_PARSER = r"[\w.-]+"

    DEFAULT_PARSERS = dict((
        ("%(asctime)s", DATE_PARSER),
        ("%(created)f", FLOAT_PARSER),
        ("%(filename)s", NAME_PARSER),
        ("%(funcName)s", STRING_PARSER),
        ("%(levelname)s", LEVEL_PARSER),
        ("%(levelno)d", INT_PARSER),
        ("%(lineno)d", INT_PARSER),
        ("%(module)s", STRING_PARSER),
        ("%(msecs)d", INT_PARSER),
        ("%(message)s", ALL_PARSER),
        ("%(name)s", NAME_PARSER),
        ("%(pathname)s", PATH_PARSER),
        ("%(process)d", INT_PARSER),
        ("%(processName)d", STRING_PARSER),
        ("%(relativeCreated)d", INT_PARSER),
        ("%(thread)d", INT_PARSER),
        ("%(threadName)d", STRING_PARSER)))

    EVALUATORS = {"f": float, "d": int, "s": str}

    def __init__(self, format_string):
        self.format_string = format_string
        self._analyze_format_string()

    def to_timestamp(self, datestr):
        for f in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S",
                  "%Y-%m-%d %H:%M:%S.%f"):
            try:
                return (datetime.strptime(datestr, f)).timesamp()
            except ValueError:
                pass

        raise ValueError("cannot parse", datestr)

    def to_utc(self, timestamp):
        return float(timestamp)

    def _analyze_format_string(self):
        columns = [mo for mo in self.COLUMNS.finditer(self.format_string)]
        ranges = [(mo.end(), mo.start()) for mo in columns]

        def paren_escape(mo):
            start = mo.start()
            index = bisect(ranges, (start, 0))
            try:
                column = ranges[index]
            except IndexError:
                column = (-1, -1)

            if column[1] <= start < column[0]:
                return mo.group()
            else:
                return "\\" + mo.group()

        escaped = self.LPAREN.sub(paren_escape, self.format_string)
        escaped = self.RPAREN.sub(paren_escape, escaped)

        def replace(mo):
            obj = mo.group(0)
            try:
                result = self.DEFAULT_PARSERS[obj]
            except KeyError:
                result = self.ALL_PARSER

            return "({})".format(result)

        self.line_parser = re.compile(self.COLUMNS.sub(replace, escaped))
        self.evaluators = {
            mo.group(1): (i, self.EVALUATORS[mo.group(2)])
            for i, mo in enumerate(columns, 1)}

        self.evaluators["created"] = self.evaluators["created"][0], self.to_utc
        asc = self.evaluators.pop("asctime", None)
        if asc:
            self.evaluators["created"] = asc[0], self.to_timestamp

    def make_record(self, mo, additional, id_, prefix):
        record = {n: f(mo.group(i)) for n, (i, f) in self.evaluators.items()}
        record.update({
            "id": prefix+str(id_),
            "additional": additional
        })
        return record

    def __call__(self, lines, prefix):
        prefix = str(prefix) + "-"
        line_parser = self.line_parser
        lines = (i.rstrip() for i in lines)
        lines = (i for i in lines if i)

        last_mo = None
        i = 0
        additional = []
        try:
            line = next(lines)
            last_mo = line_parser.match(line)
            if not last_mo:
                raise ValueError("wrong parser?", line)

            while True:
                line = next(lines)
                mo = line_parser.match(line)
                if mo:
                    yield self.make_record(last_mo, additional, i, prefix)
                    i += 1
                    additional = []
                    last_mo = mo
                else:
                    additional.append(line)
        except StopIteration:
            pass

        if last_mo:
            yield self.make_record(last_mo, additional, i, prefix)
