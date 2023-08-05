import logging
from abc import ABC, abstractmethod, abstractproperty

class BackupHandler(ABC):
    @abstractmethod
    def __init__(self, snapshot_name: str, config: dict):
        pass

    @abstractmethod
    async def backup(self, backup_dst: str, backup_dst_link: str = None, *, logger: logging.Logger = None) -> list:
        pass

    @abstractmethod
    def __bool__(self) -> bool:
        pass

    @abstractproperty
    def name(self) -> str:
        pass