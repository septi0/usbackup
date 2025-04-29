import logging
import shlex
import usbackup.cmd_exec as cmd_exec
from usbackup.backup_result import UsbackupResult
from usbackup.notification_handlers.base import NotificationHandler, NotificationHandlerError

class EmailHandler(NotificationHandler):
    handler: str = 'email'
    lexicon: dict = {
        'from': {'required': True, 'type': str},
        'to': {'required': True, 'type': list},
        'command': {'type': str, 'default': 'sendmail -t'},
    }
    
    def __init__(self, config: dict, *, logger: logging.Logger):
        self._from_address: str = config["from"]
        self._email_addresses: list[str] = config["to"]
        self._email_command: list = shlex.split(config["command"])
        
        self._logger: logging.Logger = logger

    async def notify(self, job_name: str, status: str, results: list[UsbackupResult]) -> None:
        self._logger.info("* Sending notification via email")

        to = ", ".join(self._email_addresses)
        body = self._gen_email_body(job_name, status, results)
        subject = f'Backup status ({job_name}): backup {status}'

        message = f'From: {self._from_address}\nTo: {to}\nSubject: {subject}\nMIME-Version: 1.0\nContent-Type: text/html; charset=UTF-8\n\n{body}'

        try:
            await cmd_exec.exec_cmd(self._email_command, input=message)
        except Exception as e:
            raise NotificationHandlerError(f'Email exception: {e}', 1011)
        
    def _gen_email_body(self, job_name: str, status: str, results: list[UsbackupResult]) -> str:
        # loop all results and get message key
        details = [res.message for res in results if res.message]
        details = "\n".join(details)
        
        content = f'''
        <html>
            <body>
                <p>Backup job "{job_name}" finished with status "{status}".</p>
                <h3>Summary</h3>
                <table border="1" cellpadding="5" cellspacing="0">
                    <thead>
                        <tr>
                            <th>Host</th>
                            <th>Status</th>
                            <th>Elapsed</th>
                            <th>Destination</th>
                        </tr>
                    </thead>
                    <tbody>
                        {self._gen_summary_table(results)}
                    </tbody>
                </table>
                <br>
                <h3>Details</h3>
                <pre>{details}</pre>
            </body>
        </html>
        '''
        
        return content
        
    def _gen_summary_table(self, results: list[UsbackupResult]) -> str:
        summary_table = ''
        
        for result in results:
            summary_table += f'''
                <tr>
                    <td>{result.name}</td>
                    <td>{result.return_code}</td>
                    <td>{result.elapsed_time}</td>
                    <td>{result.dest}</td>
                </tr>
            '''
            
        return summary_table