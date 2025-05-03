from usbackup.services.context import UsBackupContext

__all__ = ['UsBackupResult']

class UsBackupResultModel:
    def __init__(self, context: UsBackupContext, *, message: str = None, error: Exception = None, elapsed_time: int = 0) -> None:
        self._context: UsBackupContext = context
        
        self._message: str = message
        self._error: Exception = error
        self._elapsed_time: int = elapsed_time
        
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
    def elapsed_time(self) -> int:
        return self._elapsed_time
    
    @property
    def dest(self) -> str:
        return self._context.destination
    
    @property
    def status(self) -> str:
        return self._status