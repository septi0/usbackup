import shlex
import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.report_handlers.base import ReportHandler
from usbackup.exceptions import HandlerError

class EmailHandler(ReportHandler):
    handler: str = 'email'
    
    def __init__(self, snapshot_name: str, config: dict):
        super().__init__(snapshot_name, config)
        
        self._email_addresses: list[str] = shlex.split(config.get("report.email", ""))
        self._email_command: str = shlex.split(config.get("report.email.command", "sendmail -t"))
        self._from_address: str = config.get("report.email.from", "root@localhost")
        
        self._use_handler: bool = bool(self._email_addresses)

    async def report(self, content: list | str, *, logger: logging.Logger) -> None:
        if not self._use_handler:
            raise HandlerError(f'Handler "{self._name}" not configured')
        
        logger.info("* Sending report via email")

        to = ", ".join(self._email_addresses)
        body = "\n".join(content)

        message = f'From: {self._from_address}\nTo: {to}\nSubject: Backup report for "{self._snapshot_name}" snapshot\n\n{body}'

        await cmd_exec.exec_cmd(self._email_command, input=message)