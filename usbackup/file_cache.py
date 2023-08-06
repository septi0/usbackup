import json
import os

class FileCache:
    def __init__(self, path: str):
        self._path = path
        self._cache = {}

        self._load()

    def _load(self) -> None:
        if not os.path.exists(self._path):
            self._cache = {}
            return

        with open(self._path, 'r') as f:
            self._cache = json.load(f)

    def persist(self) -> None:
        with open(self._path, 'w') as f:
            json.dump(self._cache, f)

    def get(self, key: str, default=None):
        return self._cache.get(key, default)
    
    def set(self, key, value) -> None:
        self._cache[key] = value

    def remove(self, key: str) -> None:
        self._cache.remove(key)

    def flush(self) -> None:
        self._cache = {}