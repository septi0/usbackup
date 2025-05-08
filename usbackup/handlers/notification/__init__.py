import logging
import uuid
import datetime
from abc import ABC, abstractmethod
from usbackup.models.result import ResultModel
from usbackup.models.handler_base import HandlerBaseModel

__all__ = ['NotificationHandler', 'NotificationHandlerError']

class NotificationHandler(ABC):
    handler: str = None

    def __init__(self, model: HandlerBaseModel, name: str, type: str, *, logger: logging.Logger):
        self._name: str = name
        self._type: str = type
        
        self._logger: logging.Logger = logger
        
        self._id: str = str(uuid.uuid4())

    @abstractmethod
    async def notify(self, status: str, results: list[ResultModel], *, elapsed: datetime.timedelta) -> None:
        pass

class NotificationHandlerError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code