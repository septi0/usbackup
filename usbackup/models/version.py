import datetime

__all__ = ['UsBackupVersionModel']

class UsBackupVersionModel():
    def __init__(self, version: str, full_path: str, date: datetime):
        self._version = version
        self._full_path = full_path
        self._date = date
        
    @property
    def version(self) -> str:
        return self._version
    
    @property
    def full_path(self) -> str:
        return self._full_path
    
    @property
    def date(self) -> datetime:
        return self._date
    
    def __str__(self) -> str:
        return f'{self._version} ({self._date})'