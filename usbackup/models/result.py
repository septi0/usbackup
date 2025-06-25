import datetime
from usbackup.models.path import PathModel
from usbackup.services.context import ContextService

class ResultModel:
    def __init__(self, context: ContextService, *, message: str | None = None, error: Exception | None = None, elapsed: datetime.timedelta | None = None) -> None:
        self._context: ContextService = context
        
        self._message: str | None = message
        self._error: Exception | None = error
        self._elapsed: datetime.timedelta | None = elapsed
        
        self._date: datetime.datetime = datetime.datetime.now()
    
    @property
    def name(self) -> str:
        return self._context.name
    
    @property
    def message(self) -> str | None:
        return self._message
    
    @property
    def error(self) -> Exception | None:
        return self._error
    
    @property
    def elapsed(self) -> datetime.timedelta | None:
        return self._elapsed
    
    @property
    def dest(self) -> PathModel:
        return self._context.destination
    
    @property
    def date(self) -> datetime.datetime:
        return self._date
    
    def set_message(self, message: str) -> None:
        self._message = message