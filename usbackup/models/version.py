import datetime

__all__ = ['UsBackupVersionModel']

class UsBackupVersionModel():
    def __init__(self, version: str, path: str, date: datetime):
        self._version: str = version
        self._path: str = path
        self._date = date
        
    @property
    def version(self) -> str:
        return self._version
    
    @property
    def path(self) -> str:
        return self._path
    
    @property
    def date(self) -> datetime:
        return self._date
    
    def __str__(self) -> str:
        return self._version