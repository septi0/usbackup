
__all__ = ['UsBackupResult']

class UsBackupResultModel:
    def __init__(self, name: str, *, message: str = None, error: Exception = None, elapsed_time: int = 0, dest: str = '') -> None:
        self._name: str = name
        
        self._message: str = message
        self._error: Exception = error
        self._elapsed_time: int = elapsed_time
        self._dest: str = dest
        
        self._status = 'failed' if error else 'ok'
    
    @property
    def name(self) -> str:
        return self._name
    
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
        return self._dest
    
    @property
    def status(self) -> str:
        return self._status