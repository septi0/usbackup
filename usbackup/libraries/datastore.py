import fcntl
import logging
import shelve
from contextlib import contextmanager
from typing import Any, Callable, Generator

class Datastore:
    def __init__(self, filename: str):
        self._filename = filename

    @contextmanager
    def _open(self) -> Generator[shelve.Shelf, None, None]:
        # dbm backends do not support concurrent access, so processes take turns via an exclusive file lock
        with open(f'{self._filename}.lock', 'a') as lock_file:
            fcntl.flock(lock_file, fcntl.LOCK_EX)
            
            with shelve.open(self._filename) as db:
                yield db
    
    def get(self, key: str, default: Any = None) -> Any:
        with self._open() as db:
            return self._read(db, key, default)
    
    def update(self, key: str, update: Callable[[Any], Any], default: Any = None) -> Any:
        """
        Atomically replace the value of key with update(current value). Returns the new value.
        """
        with self._open() as db:
            value = update(self._read(db, key, default))
            db[key] = value
            
            return value

    def set(self, key: str, value: Any) -> None:
        with self._open() as db:
            db[key] = value
            
    def delete(self, key: str):
        with self._open() as db:
            if key in db:
                del db[key]
            else:
                raise KeyError(f"Key '{key}' not found in datastore.")
            
    def clear(self) -> None:
        with self._open() as db:
            db.clear()

    def keys(self) -> list[str]:
        with self._open() as db:
            return list(db.keys())

    def items(self) -> list[tuple[str, Any]]:
        with self._open() as db:
            return list(db.items())

    def values(self) -> list[Any]:
        with self._open() as db:
            return list(db.values())
    
    def _read(self, db: shelve.Shelf, key: str, default: Any) -> Any:
        if key not in db:
            return default
        
        try:
            return db[key]
        except Exception as e:
            # Unpickling can fail if a stored class's __init__ signature changed
            logging.warning(f'Datastore value "{key}" could not be read and is ignored: {e}')
            return default