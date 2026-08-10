import shelve
from typing import Any

class Datastore:
    def __init__(self, filename: str):
        self._filename = filename

    def get(self, key: str, default: Any = None) -> Any:
        with shelve.open(self._filename) as db:
            if key in db:
                try:
                    return db[key]
                except Exception:
                    # Unpickling can fail if a stored class's __init__ signature changed
                    return default
            else:
                return default

    def set(self, key: str, value: Any) -> None:
        with shelve.open(self._filename) as db:
            db[key] = value
            
    def delete(self, key: str):
        with shelve.open(self._filename) as db:
            if key in db:
                del db[key]
            else:
                raise KeyError(f"Key '{key}' not found in datastore.")
            
    def clear(self) -> None:
        with shelve.open(self._filename) as db:
            db.clear()

    def keys(self) -> list[str]:
        with shelve.open(self._filename) as db:
            return list(db.keys())

    def items(self) -> list[tuple[str, Any]]:
        with shelve.open(self._filename) as db:
            return list(db.items())

    def values(self) -> list[Any]:
        with shelve.open(self._filename) as db:
            return list(db.values())