import logging
from abc import ABC, abstractmethod, abstractproperty

class ReportHandler(ABC):

    @abstractmethod
    def __init__(self, snapshot_name: str, config: dict):
        pass

    @abstractmethod
    def report(self, content: list | str, *, logger: logging.Logger) -> None:
        pass

    @abstractmethod
    def __bool__(self) -> bool:
        pass

    @abstractproperty
    def name(self) -> str:
        pass
