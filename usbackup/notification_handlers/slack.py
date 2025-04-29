import logging
from usbackup.arequest import arequest_post
from usbackup.notification_handlers.base import NotificationHandler, NotificationHandlerError

class SlackHandler(NotificationHandler):
    handler: str = 'slack'
    lexicon: dict = {
        'token': {'required': True, 'type': str},
        'channel': {'required': True, 'type': list},
    }
    
    def __init__(self, config: dict):
        self._slack_api_url = 'https://slack.com/api/files.upload'

        self._slack_token: str = config.get("token")
        self._slack_channel: str = config.get("channel")

    async def send(self, content: list, *, logger: logging.Logger) -> None:
        logger.info("* Sending notification via slack")

        headers = {
            'Authorization': f"Bearer {self._slack_token}",
        }

        params = {
            'channels': self._slack_channel,
            # 'content': "\n".join(content),
            'filename': 'backup_report.log',
            'initial_comment': f'*Backup report for "{self._snapshot_name}" snapshot:*',
        }

        files = {
            'file': "\n".join(content),
        }

        resp = await arequest_post(self._slack_api_url, headers=headers, params=params, files=files)

        if resp.status_code != 200 or not resp.json().get('ok'):
            raise NotificationHandlerError(f'Slack exception: code: {resp.status_code}, response: {resp.text}', 1001)