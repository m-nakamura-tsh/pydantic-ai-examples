import os
import uuid
import asyncio
from typing import Optional
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.web.async_client import AsyncWebClient

from slack_bot.models import init_db, TaskRepository
from slack_bot.background_task import TaskManager

from dotenv import load_dotenv

load_dotenv()


class SlackBot:
    def __init__(self, app_token: str, bot_token: str):
        self.app = AsyncApp(token=bot_token)
        self.client = self.app.client
        self.socket_mode_handler = AsyncSocketModeHandler(self.app, app_token)
        self.task_manager = TaskManager(slack_bot=self)
        Session = init_db()
        self.task_repository = TaskRepository(Session)

        self._register_handlers()

    def _register_handlers(self):
        @self.app.event("app_mention")
        async def handle_app_mention(event, client, ack):
            await ack()

            text = event.get("text", "")
            channel = event.get("channel")
            thread_ts = event.get("ts")
            user = event.get("user")

            if "run_task" in text:
                request_message = text.replace("run_task", "")
                await self._handle_run_task(
                    channel, thread_ts, user, client, request_message=request_message
                )
            else:
                "利用方法を説明"
                await client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text="メンション時のメッセージは `run_task` から始めて下さい。続けて、要約したいesa（tsh-worldワークスペース）のURLを含んだ要約の依頼メッセージを記載して下さい \n 例： run_task 記事 https://tsh-world.esa.io/posts/5616 の内容を要約して下さい。",
                )

        @self.app.action("approve_task")
        async def handle_approve(ack, body, client):
            await ack()
            await self._handle_approval(body, client, approved=True)

        @self.app.action("retry_task")
        async def handle_reject(ack, body, client):
            await ack()

            await client.views_open(
                trigger_id=body["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": "rejection_modal",
                    "private_metadata": body["actions"][0]["value"],
                    "title": {"type": "plain_text", "text": "タスクの拒否"},
                    "submit": {"type": "plain_text", "text": "送信"},
                    "close": {"type": "plain_text", "text": "キャンセル"},
                    "blocks": [
                        {
                            "type": "input",
                            "block_id": "rejection_reason",
                            "element": {
                                "type": "plain_text_input",
                                "action_id": "reason_input",
                                "multiline": True,
                                "placeholder": {
                                    "type": "plain_text",
                                    "text": "拒否の理由を入力してください",
                                },
                            },
                            "label": {"type": "plain_text", "text": "拒否理由"},
                        }
                    ],
                },
            )

        @self.app.view("rejection_modal")
        async def handle_rejection_submission(ack, body, client, view):
            await ack()

            task_id = view["private_metadata"]
            rejection_reason = view["state"]["values"]["rejection_reason"][
                "reason_input"
            ]["value"]

            await self._handle_approval(
                body,
                client,
                approved=False,
                retry_reason=rejection_reason,
                task_id=task_id,
            )

    async def _handle_run_task(
        self,
        channel: str,
        thread_ts: str,
        user: str,
        client: AsyncWebClient,
        request_message: str,
    ):
        task_id = str(uuid.uuid4())

        # TaskRepositoryを使用してタスクを作成
        task = self.task_repository.create_task(
            task_id=task_id, channel_id=channel, thread_ts=thread_ts, user_id=user
        )

        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"タスク {task_id[:8]} を開始しました...",
        )

        # ここで LLM に仕事を依頼する
        await self.task_manager.do_summarize(
            task_id=task.task_id, message=request_message
        )

    async def request_feedback_to_user(self, task_id: str, message: str):
        # TaskRepositoryを使用してステータスを更新
        task = self.task_repository.set_awaiting_confirmation(task_id)

        if not task:
            return

        await self.client.chat_postMessage(
            channel=task.channel_id,
            thread_ts=task.thread_ts,
            text=f"タスク {task_id[:8]} の実行中に確認が必要な状況になりました。",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*タスク {task_id[:8]}* の結果にフィードバックしますか？\n 結果：\n{message}",
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "承認"},
                            "style": "primary",
                            "action_id": "approve_task",
                            "value": task_id,
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "リトライ"},
                            "style": "danger",
                            "action_id": "retry_task",
                            "value": task_id,
                        },
                    ],
                },
            ],
        )

    async def _handle_approval(
        self,
        body: dict,
        client: AsyncWebClient,
        approved: bool,
        retry_reason: Optional[str] = None,
        task_id: Optional[str] = None,
    ):
        if not task_id:
            task_id = body["actions"][0]["value"] if "actions" in body else None

        if not task_id:
            return

        # TaskRepositoryを使用してタスクを取得・更新
        if approved:
            task = self.task_repository.approve_task(task_id)
            response_text = (
                f"タスク {task_id[:8]} の結果を承認しました。処理を終了します"
            )
        else:
            task = self.task_repository.retry_task(task_id, retry_reason or "")
            response_text = f"タスク {task_id[:8]} にフィードバックがありました。\nフィードバック: {retry_reason}"

        if not task:
            return

        channel = task.channel_id
        thread_ts = task.thread_ts

        await client.chat_postMessage(
            channel=channel, thread_ts=thread_ts, text=response_text
        )

        print(f"Task {task_id} - Is Approved: {approved}")
        if retry_reason:
            print(f"Retry reason: {retry_reason}")

        if not approved:
            # ここで LLM にフィードバックの依頼する
            await self.task_manager.do_feedback(task_id=task_id, message=retry_reason)

    async def start(self):
        await self.socket_mode_handler.start_async()


async def main():
    app_token = os.environ.get("SLACK_APP_TOKEN")
    bot_token = os.environ.get("SLACK_BOT_TOKEN")

    if not app_token or not bot_token:
        raise ValueError(
            "SLACK_APP_TOKEN and SLACK_BOT_TOKEN must be set in environment variables"
        )

    bot = SlackBot(app_token, bot_token)

    try:
        await bot.start()
    except KeyboardInterrupt:
        bot.shutdown()
        print("Bot shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
