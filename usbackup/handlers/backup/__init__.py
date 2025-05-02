import logging
import uuid
from abc import ABC, abstractmethod
from usbackup.models.handler_base import UsBackupHandlerBaseModel
from usbackup.models.remote import RemoteModel
from usbackup.libraries.cleanup_queue import CleanupQueue

__all__ = ['BackupHandler', 'BackupHandlerError']

class BackupHandler(ABC):
    handler: str = None
    
    def __init__(self, host: RemoteModel, model: UsBackupHandlerBaseModel, *, cleanup: CleanupQueue, logger: logging.Logger):
        self._cleanup: CleanupQueue = cleanup
        self._logger: logging.Logger = logger
        
        self._id: str = str(uuid.uuid4())

    @abstractmethod
    async def backup(self, backup_dst: str, backup_dst_link: str = None) -> None:
        pass
    
class BackupHandlerError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code