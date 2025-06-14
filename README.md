# larch-lib

A collection of useful Python utilities and components, organized under the `larch` namespace. This library provides tools for registry patterns, advanced logging, gevent-based concurrency, testing, and various utility functions for robust Python development.

## Features

- **Registry Pattern**: Type-dependent registry for adapters and factories (`larch.lib.adapter`).
- **Advanced Logging**: Pretty-printing log formatter, log file parsing, and logging configuration helpers (`larch.lib.logging`).
- **Gevent Utilities**: Concurrency primitives, throttling, debouncing, and queue implementations for gevent-based applications (`larch.lib.gevent`).
- **Testing Helpers**: Logging configuration and expectation utilities for tests (`larch.lib.test`).
- **General Utilities**: Deep dictionary updates, string/object conversion, performance monitoring, and more (`larch.lib.utils`).

## Installation

Install via pip (editable mode recommended for development):

```bash
pip install -e .[dev]
```

Or for regular use:

```bash
pip install .
```

## Usage

### Registry Example
```python
from larch.lib.adapter import Registry

class From: pass
class To: pass
class Adapter: pass

registry = Registry()
registry.register(From, To, "", Adapter)
adapter_cls = registry.get(From, To)
```

### Logging Example
```python
from larch.lib.logging import PPFormater
import logging

logging.basicConfig(format='%(message)s')
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
logger.handlers[0].setFormatter(PPFormater('%(message)s'))
logger.info({'a': [1, 2, 3]})
```

### Gevent Queue Example
```python
from larch.lib.gevent import Queue
q = Queue(10)
q.put('item')
item = q.get()
```

## Testing

Run all tests:

```bash
python -m unittest discover tests
```

Or use the provided runner:

```bash
python tests/run.py
```

## Project Structure

- `larch/lib/adapter.py` — Registry pattern implementation
- `larch/lib/logging/` — Logging utilities and formatters
- `larch/lib/gevent/` — Gevent-based concurrency tools
- `larch/lib/test/` — Test helpers and logging config
- `larch/lib/utils/` — General-purpose utilities
- `tests/` — Unit tests for all modules

## License

MIT License. See `pyproject.toml` for details.

---

For more details, see the source code and docstrings in each module.
