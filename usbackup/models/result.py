from usbackup.services.context import ContextService

class ResultModel:
    def __init__(self, context: ContextService, *, message: str = None, error: Exception = None, elapsed: int = 0) -> None:
        self._context: ContextService = context
        
        self._message: str = message
        self._error: Exception = error
        self._elapsed: int = elapsed
        
        self._status = 'failed' if error else 'ok'
    
    @property
    def name(self) -> str:
        return self._context.name
    
    @property
    def message(self) -> str:
        return self._message
    
    @property
    def error(self) -> Exception:
        return self._error
    
    @property
    def elapsed(self) -> int:
        return self._elapsed
    
    @property
    def dest(self) -> str:
        return self._context.destination
    
    @property
    def status(self) -> str:
        return self._status