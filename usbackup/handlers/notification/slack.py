import datetime
from usbackup.libraries.arequest import arequest_post
from usbackup.models.result import ResultModel
from usbackup.handlers.notification import HandlerBaseModel, NotificationHandler, NotificationHandlerError

class SlackHandlerModel(HandlerBaseModel):
    handler: str = 'slack'
    token: str
    channel: str

class SlackHandler(NotificationHandler):
    handler: str = 'slack'

    def __init__(self, model: SlackHandlerModel, *args, **kwargs) -> None:
        super().__init__(model, *args, **kwargs)

        self._slack_token: str = model.token
        self._slack_channel: str = model.channel

        self._slack_get_url = "https://slack.com/api/files.getUploadURLExternal"
        self._slack_complete_url = "https://slack.com/api/files.completeUploadExternal"

    async def notify(self, status: str, results: list[ResultModel], *, elapsed: datetime.timedelta) -> None:
        details = [res.message for res in results if res.message]
        details = "\n".join(details)
        file = details.encode("utf-8")
        filename = 'report.log'

        headers = {
            "Authorization": f"Bearer {self._slack_token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        payload = {
            "filename": filename,
            "length": len(file),
        }

        resp = await arequest_post(self._slack_get_url, headers=headers, params=payload)

        if resp.status_code != 200 or not resp.json().get("ok"):
            raise NotificationHandlerError(f"Slack exception: code: {resp.status_code}, response: {resp.text}", 1001)

        resp_json = resp.json()
        upload_url = resp_json["upload_url"]
        file_id = resp_json["file_id"]

        upload_resp = await arequest_post(upload_url, data=file)

        if upload_resp.status_code != 200:
            raise NotificationHandlerError(f"Slack upload exception: code: {upload_resp.status_code}, response: {upload_resp.text}", 1002)

        payload = {
            "files": [
                {
                    "id": file_id,
                    "title": filename,
                }
            ],
            "channels": self._slack_channel,
            "initial_comment": f'*{self._type.capitalize()} job "{self._name}" status: {status} (Elapsed: {elapsed})*',
        }

        send_resp = await arequest_post(self._slack_complete_url, headers=headers, json=payload)

        if send_resp.status_code != 200 or not send_resp.json().get("ok"):
            raise NotificationHandlerError(f"Slack exception: code: {send_resp.status_code}, response: {send_resp.text}", 1003)
