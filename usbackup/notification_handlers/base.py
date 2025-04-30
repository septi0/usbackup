import logging
import uuid
from abc import ABC, abstractmethod
from usbackup.backup_result import UsbackupResult

class NotificationHandler(ABC):
    handler: str = None
    lexicon: dict = {}
    
    def __init__(self, config: dict, *, logger: logging.Logger):
        self._config: dict = config
        
        self._logger: logging.Logger = logger
        
        self._id: str = str(uuid.uuid4())

    @abstractmethod
    async def notify(self, job_name: str, status: str, results: list[UsbackupResult]) -> None:
        pass

    @property
    def name(self) -> str:
        return self.handler

class NotificationHandlerError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code