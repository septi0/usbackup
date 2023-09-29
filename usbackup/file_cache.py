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
        # create parent dir if it doesn't exist
        parent_dir = os.path.dirname(self._path)

        if not os.path.exists(parent_dir):
            os.makedirs(parent_dir)

        # write cache to file
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