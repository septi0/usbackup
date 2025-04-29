import logging
from usbackup.backup_result import UsbackupResult
from usbackup.notification_handlers.base import NotificationHandler

__all__ = ['UsbackupNotifier']

class UsbackupNotifier:
    def __init__(self, handlers: list[NotificationHandler], *, logger: logging.Logger):
        self._handlers: list[NotificationHandler] = handlers
        
        self._logger: logging.Logger = logger

    async def notify(self, name: str, results: list[UsbackupResult], *, notification_policy: str = None) -> None:
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
                self._logger.info(f'Sending notification via "{handler.name}" handler')
                await handler.notify(name, status, results)
            except Exception as e:
                self._logger.error(f"Failed to send notification via {handler.name}: {e}")