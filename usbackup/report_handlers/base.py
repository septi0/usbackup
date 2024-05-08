import logging
from abc import ABC, abstractmethod, abstractproperty

class ReportHandler(ABC):
    handler: str = None

    def __init__(self, snapshot_name: str, config: dict):
        self._snapshot_name:str = snapshot_name
        
        self._use_handler: bool = False

    @abstractmethod
    async def report(self, content: list | str, *, logger: logging.Logger) -> None:
        pass

    def __bool__(self) -> bool:
        return self._use_handler

    @property
    def name(self) -> str:
        return self.handler