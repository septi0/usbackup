from abc import ABC, abstractmethod, abstractproperty

class BackupHandler(ABC):
    handler: str = None
    lexicon: dict = {}

    @abstractmethod
    async def backup(self, backup_dst: str, backup_dst_link: str = None) -> None:
        pass

    @property
    def name(self) -> str:
        return self.handler
    
class BackupHandlerError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code