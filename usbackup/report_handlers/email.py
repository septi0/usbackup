import shlex
import logging
import usbackup.cmd_exec as cmd_exec
from usbackup.report_handlers.base import ReportHandler
from usbackup.exceptions import HandlerError

class EmailHandler(ReportHandler):
    def __init__(self, snapshot_name: str, config: dict):
        self._name: str = 'email'

        self._snapshot_name: str = snapshot_name
        self._email_addresses: list[str] = shlex.split(config.get("report_email", ""))
        self._email_command: str = shlex.split(config.get("report_email.command", "sendmail -t"))
        self._from_address: str = config.get("report_email.from", "root@localhost")

    def report(self, content: list | str, *, logger: logging.Logger) -> None:
        if not bool(self._email_addresses):
            raise HandlerError(f'Handler "{self._name}" not configured')
        
        logger.info("* Sending report via email")

        to = ", ".join(self._email_addresses)
        body = "\n".join(content)

        message = f'From: {self._from_address}\nTo: {to}\nSubject: Backup report for "{self._snapshot_name}" snapshot\n\n{body}'

        cmd_exec.exec_cmd(self._email_command, input=message.encode())

    def __bool__(self) -> bool:
        return bool(self._email_addresses)

    @property
    def name(self) -> str:
        return self._name