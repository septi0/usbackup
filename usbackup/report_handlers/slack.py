import requests
import logging
from usbackup.report_handlers.base import ReportHandler
from usbackup.exceptions import HandlerError

class SlackHandler(ReportHandler):
    def __init__(self, snapshot_name: str, config: dict):
        self._name: str = 'slack'
        self._snapshot_name: str = snapshot_name
        self._slack_api_url = 'https://slack.com/api/files.upload'

        self._slack_channel: str = config.get("report_slack", "")
        self._slack_token: str = config.get("report_slack.token", "")

    def report(self, content: list, *, logger: logging.Logger) -> None:
        if not bool(self._slack_channel):
            raise HandlerError(f'Handler "{self._name}" not configured')

        logger.info("* Sending report via slack")

        headers = {
            'Authorization': f"Bearer {self._slack_token}",
        }

        data = {
            'channels': self._slack_channel,
            'content': "\n".join(content),
            'filename': 'backup_report.log',
            'initial_comment': f'*Backup report for "{self._snapshot_name}" snapshot:*',
        }

        resp = requests.post(self._slack_api_url, headers=headers, params=data)

        if resp.status_code != 200 or not resp.json().get('ok'):
            raise Exception(f'Slack exception: code: {resp.status_code}, response: {resp.text}')

    def __bool__(self) -> bool:
        return bool(self._slack_channel)

    @property
    def name(self) -> str:
        return self._name