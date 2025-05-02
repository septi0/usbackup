import logging
import uuid
from abc import ABC, abstractmethod
from usbackup.models.result import UsBackupResultModel
from usbackup.models.handler_base import UsBackupHandlerBaseModel

__all__ = ['NotificationHandler', 'NotificationHandlerError']

class NotificationHandler(ABC):
    handler: str = None

    def __init__(self, model: UsBackupHandlerBaseModel, *, logger: logging.Logger):
        self._logger: logging.Logger = logger
        
        self._id: str = str(uuid.uuid4())

    @abstractmethod
    async def notify(self, job_name: str, status: str, results: list[UsBackupResultModel]) -> None:
        pass

class NotificationHandlerError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code