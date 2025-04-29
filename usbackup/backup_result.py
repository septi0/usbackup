
__all__ = ['UsbackupResult']

class UsbackupResult:
    def __init__(self, name: str, *, return_code: int, message: str, elapsed_time: int = 0, dest: str = '') -> None:
        self._name: str = name
        
        self._return_code: int = return_code
        self._message: str = message
        self._elapsed_time: int = elapsed_time
        self._dest: str = dest
    
    @property
    def name(self) -> str:
        return self._name
        
    @property
    def return_code(self) -> int:
        return self._return_code
    
    @property
    def message(self) -> str:
        return self._message
    
    @property
    def elapsed_time(self) -> int:
        return self._elapsed_time
    
    @property
    def dest(self) -> str:
        return self._dest