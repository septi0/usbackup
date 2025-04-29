import json
import os

class FileCache:
    def __init__(self, path: str = None):
        self._path = self._gen_path(path)
        self._cache = self._load()
        
    def _gen_path(self, path: str) -> str:
        if path:
            return path
        
        if os.getuid() == 0:
            return '/var/cache/usbackup/filecache.json'
        else:
            return os.path.expanduser('~/.cache/usbackup/filecache.json')

    def _load(self, path: str = None) -> None:
        if not os.path.exists(self._path):
            return {}

        with open(self._path, 'r') as f:
            return json.load(f)

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