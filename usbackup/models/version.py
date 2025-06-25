import datetime
from usbackup.models.path import PathModel

class BackupVersionModel():
    def __init__(self, version: str, path: PathModel, date: datetime.datetime) -> None:
        self._version: str = version
        self._path: PathModel = path
        self._date: datetime.datetime = date
        
    @property
    def version(self) -> str:
        return self._version
    
    @property
    def path(self) -> PathModel:
        return self._path
    
    @property
    def date(self) -> datetime.datetime:
        return self._date
    
    def __str__(self) -> str:
        return self._version