"""Bounded single-process login admission; not a distributed production limiter."""
import hashlib
import threading
import time


class LoginThrottled(Exception):
    pass


class LoginThrottle:
    def __init__(self, *, identity_limit=5, source_limit=30, window=900,
                 max_buckets=4096, clock=time.monotonic):
        if (any(type(value) is not int or value < 1 for value in
                (identity_limit, source_limit, window))
                or type(max_buckets) is not int or max_buckets < 2):
            raise ValueError('Invalid local login throttle limits')
        self.identity_limit, self.source_limit = identity_limit, source_limit
        self.window, self.max_buckets, self.clock = window, max_buckets, clock
        self._buckets = {}
        self._lock = threading.Lock()

    def _prune(self, now):
        cutoff = now - self.window
        for key, entries in list(self._buckets.items()):
            for token, (started, failed) in list(entries.items()):
                if started <= cutoff:
                    del entries[token]
            if not entries:
                del self._buckets[key]

    def reserve(self, client, email):
        # Names/addresses never become raw keys or persisted throttle records.
        source = ('source', hashlib.sha256(client.encode('utf-8')).hexdigest())
        identity = ('identity', hashlib.sha256((client + '\0' + email).encode('utf-8')).hexdigest())
        with self._lock:
            now = self.clock()
            self._prune(now)
            if (len(self._buckets.get(source, {})) >= self.source_limit
                    or len(self._buckets.get(identity, {})) >= self.identity_limit):
                raise LoginThrottled()
            needed = sum(key not in self._buckets for key in (source, identity))
            if len(self._buckets) + needed > self.max_buckets:
                # Never evict another client's live limit to admit a new identity.
                raise LoginThrottled()
            token = object()
            for key in (source, identity):
                self._buckets.setdefault(key, {})[token] = (now, False)
            return source, identity, token

    def finish(self, reservation, success):
        source, identity, token = reservation
        with self._lock:
            self._prune(self.clock())
            for key in (source, identity):
                entries = self._buckets.get(key)
                if not entries or token not in entries:
                    continue
                if success:
                    del entries[token]
                    if key == identity:
                        # Reset this identity's completed failures, preserving
                        # other in-flight requests and source-wide failures.
                        for previous, (_, failed) in list(entries.items()):
                            if failed:
                                del entries[previous]
                else:
                    entries[token] = (entries[token][0], True)
                if not entries:
                    del self._buckets[key]
