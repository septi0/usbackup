import logging
import uuid
from abc import ABC, abstractmethod
from usbackup.remote import Remote
from usbackup.cleanup_queue import CleanupQueue

class BackupHandler(ABC):
    handler: str = None
    lexicon: dict = {}
    
    def __init__(self, src_host: Remote, config: dict, *, cleanup: CleanupQueue, logger: logging.Logger):
        self._src_host: Remote = src_host
        self._config: dict = config
        
        self._cleanup: CleanupQueue = cleanup
        self._logger: logging.Logger = logger
        
        self._id: str = str(uuid.uuid4())

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