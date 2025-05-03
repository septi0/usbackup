import logging
import uuid
from abc import ABC, abstractmethod
from usbackup.models.result import ResultModel
from usbackup.models.handler_base import HandlerBaseModel

__all__ = ['NotificationHandler', 'NotificationHandlerError']

class NotificationHandler(ABC):
    handler: str = None

    def __init__(self, model: HandlerBaseModel, *, logger: logging.Logger):
        self._logger: logging.Logger = logger
        
        self._id: str = str(uuid.uuid4())

    @abstractmethod
    async def notify(self, job_name: str, status: str, results: list[ResultModel]) -> None:
        pass

class NotificationHandlerError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code