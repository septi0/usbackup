from usbackup.report_handlers.email import EmailHandler
from usbackup.report_handlers.slack import SlackHandler

__all__ = ['list']

list = [
    EmailHandler,
    SlackHandler,
]
