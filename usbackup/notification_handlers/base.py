from abc import ABC, abstractmethod, abstractproperty
from usbackup.backup_result import UsbackupResult

class NotificationHandler(ABC):
    handler: str = None
    lexicon: dict = {}

    @abstractmethod
    async def notify(self, job_name: str, status: str, results: list[UsbackupResult]) -> None:
        pass

    @property
    def name(self) -> str:
        return self.handler

class NotificationHandlerError(Exception):
    pass