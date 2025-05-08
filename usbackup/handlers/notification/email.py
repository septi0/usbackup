import shlex
import datetime
from usbackup.libraries.cmd_exec import CmdExec
from usbackup.models.result import ResultModel
from usbackup.handlers.notification import HandlerBaseModel, NotificationHandler, NotificationHandlerError

class EmailHandlerModel(HandlerBaseModel):
    handler: str = 'email'
    sender: str
    to: list[str]
    command: str = 'sendmail -t'

class EmailHandler(NotificationHandler):
    handler: str = 'email'
    
    def __init__(self, model: EmailHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)
        
        self._from_address: str = model.sender
        self._email_addresses: list[str] = model.to
        self._email_command: list = shlex.split(model.command)

    async def notify(self, status: str, results: list[ResultModel], *, elapsed: datetime.timedelta) -> None:
        to = ", ".join(self._email_addresses)
        body = self._gen_email_body(status, results, elapsed=elapsed)
        subject = f'{self._type.capitalize()} job "{self._name}" status: {status}'

        message = f'From: {self._from_address}\nTo: {to}\nSubject: {subject}\nMIME-Version: 1.0\nContent-Type: text/html; charset=UTF-8\n\n{body}'

        try:
            await CmdExec.exec(self._email_command, input=message)
        except Exception as e:
            raise NotificationHandlerError(f'Email exception: {e}', 1011)
        
    def _gen_email_body(self, status: str, results: list[ResultModel], *, elapsed: datetime.timedelta) -> str:
        summary_table = ''
        details = ''
        
        for result in results:
            if not result.error:
                status_str = '<strong style="color:green;">OK</strong>'
            else:
                status_str = f'<strong style="color:red;">Failed</strong> <span>({result.error})</span>'
            
            summary_table += f'''
                <tr>
                    <td>{result.name}</td>
                    <td>{status_str}</td>
                    <td>{result.elapsed}</td>
                    <td>{result.dest}</td>
                </tr>
            '''
            
            details += f'''
                <h4>{result.name}</h4>
                <pre>{result.message}</pre>
            '''
        
        content = f'''
        <html>
            <body>
                <p>{self._type.capitalize()} job "{self._name}" finished with status "{status}". Total elapsed time: {elapsed}</p>
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
                        {summary_table}
                    </tbody>
                </table>
                <br>
                <h3>Details</h3>
                {details}
            </body>
        </html>
        '''
        
        return content