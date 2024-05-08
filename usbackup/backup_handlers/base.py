import logging
from abc import ABC, abstractmethod, abstractproperty
from usbackup.remote import Remote

class BackupHandler(ABC):
    handler: str = None
    
    def __init__(self, src_host: Remote, snapshot_name: str, config: dict):
        self._src_host: Remote = src_host
        self._snapshot_name:str = snapshot_name
        
        self._use_handler: bool = False

    @abstractmethod
    async def backup(self, backup_dst: str, backup_dst_link: str = None, *, logger: logging.Logger = None) -> None:
        pass

    def __bool__(self) -> bool:
        return self._use_handler

    @property
    def name(self) -> str:
        return self.handler