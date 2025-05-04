import logging
import uuid
from abc import ABC, abstractmethod
from usbackup.libraries.cleanup_queue import CleanupQueue
from usbackup.models.handler_base import HandlerBaseModel
from usbackup.models.host import HostModel
from usbackup.models.path import PathModel

__all__ = ['BackupHandler', 'BackupHandlerError']

class BackupHandler(ABC):
    handler: str = None
    
    def __init__(self, model: HandlerBaseModel, host: HostModel, *, cleanup: CleanupQueue, logger: logging.Logger):
        self._host: HostModel = host
        
        self._cleanup: CleanupQueue = cleanup
        self._logger: logging.Logger = logger
        
        self._id: str = str(uuid.uuid4())

    @abstractmethod
    async def backup(self, backup_dst: PathModel, backup_dst_link: str = PathModel) -> None:
        pass
    
class BackupHandlerError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code