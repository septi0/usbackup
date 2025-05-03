import logging
from usbackup.models.result import UsBackupResultModel
from usbackup.handlers.notification import NotificationHandler

__all__ = ['UsbackupNotifier']
class UsbackupNotifier:
    def __init__(self, handlers: list[NotificationHandler], *, logger: logging.Logger):
        self._handlers: list[NotificationHandler] = handlers
        
        self._logger: logging.Logger = logger

    async def notify(self, name: str, type: str, results: list[UsBackupResultModel], *, notification_policy: str = None) -> None:
        errors = any(result.status != 'ok' for result in results)
        status = 'ok' if not errors else 'failed'
        
        if notification_policy == 'never':
            return
        elif notification_policy == 'on-failure':
            if not errors:
                return
        
        if not self._handlers:
            self._logger.warning("No notification handlers configured")
            return
        
        for handler in self._handlers:
            try:
                self._logger.info(f'Sending notification via "{handler.handler}" handler')
                await handler.notify(name, status, results)
            except Exception as e:
                self._logger.error(f"Failed to send notification via {handler.handler}: {e}")