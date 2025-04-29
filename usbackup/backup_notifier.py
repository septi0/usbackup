import logging
from usbackup.backup_result import UsbackupResult
from usbackup.notification_handlers.base import NotificationHandler

__all__ = ['UsbackupNotifier']

class UsbackupNotifier:
    def __init__(self, handlers: list[NotificationHandler], *, logger: logging.Logger):
        self._handlers: list[NotificationHandler] = handlers
        
        self._logger: logging.Logger = logger
            
    async def notify(self, name: str, status: str, results: list[UsbackupResult]) -> None:
        if not self._handlers:
            self._logger.warning("No notification handlers configured")
            return
        
        for handler in self._handlers:
            try:
                await handler.notify(name, status, results)
            except Exception as e:
                self._logger.error(f"Failed to send notification via {handler.name}: {e}")