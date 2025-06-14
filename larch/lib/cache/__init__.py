from collections import OrderedDict
from collections.abc import MutableMapping


class LIRSStack:
    def __init__(self, lirs, hirs, s=None, q=None):
        self.lirs = lirs
        self.hirs = hirs
        self.s = OrderedDict() if s is None else s
        self.q = OrderedDict() if q is None else q

    def clear(self):
        self.s.clear()
        self.q.clear()

    def remove(self, key):
        s = self.s
        q = self.q

        status = s.pop(key, None)
        if status == 0:
            try:
                new_lirs = q.popitem(0)[0]
            except KeyError:
                # no resident hirs block => remove all hirs blocks from s
                for k, v in list(s.items()):
                    if v == 1:
                        del s[k]
            else:
                # hirs to lirs
                s[new_lirs] = 0
                self.prune()

        q.pop(key, None)

    def hit(self, key):
        """hits the key and returns an evicted key or None"""
        to_evict = None
        s = self.s
        q = self.q

        # 0 is lirs status
        # 1 is hirs status

        status = s.pop(key, None)
        if status == 0:  # lirs block
            # move to top of s
            s[key] = 0

            self.prune()

        elif status == 1:  # hirs block
            if not q.pop(key, False):
                # non resident hirs block
                if len(q) >= self.hirs > 0:
                    # remove block from front of q
                    to_evict = q.popitem(0)[0]

            # move to top of s and change status to lirs
            s[key] = 0

            # remove last lirs from s and add to q's end
            q[s.popitem(0)[0]] = True

            self.prune()

        else:  # key not in s
            if q.pop(key, False):  # resident hirs block
                # move to the top of s with hirs status
                s[key] = 1

                # move to end of q
                q[key] = True

            elif len(s) < self.lirs:  # below capacity
                # give it lirs status
                s[key] = 0

            else:  # non resident hirs block
                if len(q) >= self.hirs > 0:
                    # remove block from front of q
                    to_evict = q.popitem(0)[0]

                # add to top of s with hirs status
                s[key] = 1

                # add to end of q
                q[key] = True

        return to_evict

    def prune(self):
        s = self.s
        while True:
            # pop items from s until s is in lirs status
            for key, v in s.items():
                if v == 0:  # lirs
                    return
                s.pop(key, None)
                break
            else:
                break  # nothing to prune

    def evict(self):
        # yield all possible blocks to evict
        while self.q:
            key = self.q.popitem(0)[0]
            self.s.pop(key, None)
            yield key

        while self.s:
            key, value = self.s.popitem(0)
            if value == 0:
                self.prune()
                yield key

    def next_to_evict(self):
        if self.q:
            return next(iter(self.q.keys()))

        if self.s:
            return next(iter(self.s.keys()))

        raise ValueError()


class LIRSCache(MutableMapping):
    def __init__(self, lirs, hirs):
        self._data = {}
        self._stack = LIRSStack(lirs, hirs)

    def clear(self):
        self._data.clear()
        self._stack.clear()

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data

    def get(self, key, default=None):
        # stack is for sure not a member of data
        result = self._data.get(key, self._stack)
        if result is self._stack:
            return default

        self._hit(key)
        return self._data[key]

    def pop(self, key, default=None):
        self._stack.remove(key)
        return self._data.pop(key, default)

    def __setitem__(self, key, item):
        self._hit(key)
        self._data[key] = item

    def __getitem__(self, key):
        result = self._data[key]
        self._hit(key)
        return result

    def __delitem__(self, key):
        del self._data[key]
        self._stack.remove(key)

    def __iter__(self):
        return iter(self._data)

    def _hit(self, key):
        to_evict = self._stack.hit(key)
        if to_evict is not None:
            self._evict(to_evict)

    def _evict(self, to_evict):
        return self._data.pop(to_evict, None)

    def next_to_evict(self):
        return self._stack.next_to_evict()


class LRUCache(MutableMapping):
    """A simple LRU Cache max_size is the size in bytes."""

    def __init__(self, max_size=10000, min_count=100,
                 remove_callback=None, sizeof=lambda k: 1):
        self._max_size = max_size
        self._size = 0
        self._min_count = min_count
        self._remove_callback = remove_callback or (lambda k, v: None)
        self._d = OrderedDict()
        self.sizeof = sizeof

    @property
    def size(self):
        return self._size

    def __getitem__(self, key):
        value = self._d.pop(key)
        self._d[key] = value
        return value

    def __setitem__(self, key, value):
        if key in self._d:
            self._size -= self.sizeof(self._d.pop(key))

        size = self.sizeof(value)
        if size < self._max_size:
            self._d[key] = value
            self._size += size
            self._prune()

    def __delitem__(self, key):
        val = self._d.pop(key)
        self._size -= self.sizeof(val)
        self._remove_callback(key, val)

    def __len__(self):
        return len(self._d)

    def __iter__(self):
        return iter(self._d.keys())

    def values(self):
        return self._d.values()

    def _prune(self):
        while self._size > self._max_size and len(self._d) > self._min_count:
            k, v = self._d.popitem(False)
            self._size -= self.sizeof(v)
            self._remove_callback(k, v)

    def clear(self):
        for i in list(self._d.items()):
            self._remove_callback(*i)

        self._size = 0
        self._d.clear()
