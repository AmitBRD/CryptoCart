class Proxy:
    def __init__(self, obj, pool):
        self._obj = obj
        self._pool = pool

    def __enter__(self):
        return self._obj

    def __exit__(self, typ, val, tb):
        self._pool._put(self._obj)


class Pool:
    """Pool of objects"""
    def __init__(self, queue):
        self._queue = queue

    def lease(self):
        return Proxy(self._queue.get(False), self)

    def _put(self, obj):
        self._queue.put(obj)