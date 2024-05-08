import logging
from usbackup.arequest import arequest_post
from usbackup.report_handlers.base import ReportHandler
from usbackup.exceptions import HandlerError

class SlackHandler(ReportHandler):
    handler: str = 'slack'
    
    def __init__(self, snapshot_name: str, config: dict):
        super().__init__(snapshot_name, config)
        
        self._slack_api_url = 'https://slack.com/api/files.upload'

        self._slack_channel: str = config.get("report.slack", "")
        self._slack_token: str = config.get("report.slack.token", "")
        
        self._use_handler: bool = bool(self._slack_channel)

    async def report(self, content: list, *, logger: logging.Logger) -> None:
        if not self._use_handler:
            raise HandlerError(f'Handler "{self._name}" not configured')

        logger.info("* Sending report via slack")

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
            raise Exception(f'Slack exception: code: {resp.status_code}, response: {resp.text}')