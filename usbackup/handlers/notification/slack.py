from usbackup.libraries.arequest import arequest_post
from usbackup.models.result import UsBackupResultModel
from usbackup.handlers.notification import UsBackupHandlerBaseModel, NotificationHandler, NotificationHandlerError

class SlackHandlerModel(UsBackupHandlerBaseModel):
    handler: str = 'slack'
    token: str
    channel: str

class SlackHandler(NotificationHandler):
    handler: str = 'slack'
    
    def __init__(self, model: SlackHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)
        
        self._slack_token: str = model.token
        self._slack_channel: str = model.channel
        
        self._slack_api_url = 'https://slack.com/api/files.upload'

    async def notify(self, job_name: str, status: str, results: list[UsBackupResultModel]) -> None:
        details = [res.message for res in results if res.message]
        details = "\n".join(details)

        headers = {
            'Authorization': f"Bearer {self._slack_token}",
        }

        params = {
            'channels': self._slack_channel,
            'filename': 'backup_report.log',
            'initial_comment': f'*Backup status ({job_name}): backup {status}*',
        }

        files = {
            'file': details,
        }

        resp = await arequest_post(self._slack_api_url, headers=headers, params=params, files=files)

        if resp.status_code != 200 or not resp.json().get('ok'):
            raise NotificationHandlerError(f'Slack exception: code: {resp.status_code}, response: {resp.text}', 1001)