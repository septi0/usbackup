import logging
import datetime
from usbackup.models.job import JobModel
from usbackup.models.handler_base import HandlerBaseModel
from usbackup.models.result import ResultModel
from usbackup.handlers import handler_factory

__all__ = ['NotifierService']
class NotifierService:
    def __init__(self, job: JobModel, handlers: list[HandlerBaseModel], *, logger: logging.Logger):
        self._handlers: list[HandlerBaseModel] = handlers
        
        self._logger: logging.Logger = logger
        
        self._name: str = job.name
        self._type: str = job.type
        self._notification_policy: str = job.notification_policy

    async def notify(self, results: list[ResultModel], *, elapsed: datetime.timedelta = None) -> None:
        errors = any(result.error for result in results)
        status = 'ok' if not errors else 'failed'
        
        if self._notification_policy == 'never':
            return
        elif self._notification_policy == 'on-failure':
            if not errors:
                return
        
        if not self._handlers:
            self._logger.warning("No notification handlers configured")
            return
        
        for handler_model in self._handlers:
            handler_logger = self._logger.getChild(handler_model.handler)
            
            handler = handler_factory('notification', handler_model.handler, handler_model, self._name, self._type, logger=handler_logger)
            
            try:
                self._logger.info(f'Sending notification via "{handler_model.handler}" handler')
                await handler.notify(status, results, elapsed=elapsed)
            except Exception as e:
                self._logger.error(f"Failed to send notification via {handler_model.handler}: {e}")