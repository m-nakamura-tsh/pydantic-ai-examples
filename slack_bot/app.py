import os
import re
import uuid
import asyncio
from typing import Optional
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError

from slack_bot.models import init_db, Task, TaskStatus
from slack_bot.background_task import TaskManager


class SlackBot:
    def __init__(self, app_token: str, bot_token: str):
        self.app = AsyncApp(token=bot_token)
        self.client = self.app.client
        self.socket_mode_handler = AsyncSocketModeHandler(self.app, app_token)
        self.task_manager = TaskManager()
        self.Session = init_db()
        
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
                await self._handle_run_task(channel, thread_ts, user, client)

        @self.app.action("approve_task")
        async def handle_approve(ack, body, client):
            await ack()
            await self._handle_approval(body, client, approved=True)

        @self.app.action("reject_task")
        async def handle_reject(ack, body, client):
            await ack()
            
            await client.views_open(
                trigger_id=body["trigger_id"],
                view={
                    "type": "modal",
                    "callback_id": "rejection_modal",
                    "private_metadata": body["actions"][0]["value"],
                    "title": {
                        "type": "plain_text",
                        "text": "タスクの拒否"
                    },
                    "submit": {
                        "type": "plain_text",
                        "text": "送信"
                    },
                    "close": {
                        "type": "plain_text",
                        "text": "キャンセル"
                    },
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
                                    "text": "拒否の理由を入力してください"
                                }
                            },
                            "label": {
                                "type": "plain_text",
                                "text": "拒否理由"
                            }
                        }
                    ]
                }
            )

        @self.app.view("rejection_modal")
        async def handle_rejection_submission(ack, body, client, view):
            await ack()
            
            task_id = view["private_metadata"]
            rejection_reason = view["state"]["values"]["rejection_reason"]["reason_input"]["value"]
            
            await self._handle_approval(
                body, 
                client, 
                approved=False, 
                rejection_reason=rejection_reason,
                task_id=task_id
            )

    async def _handle_run_task(self, channel: str, thread_ts: str, user: str, client: AsyncWebClient):
        task_id = str(uuid.uuid4())
        
        session = self.Session()
        task = Task(
            task_id=task_id,
            channel_id=channel,
            thread_ts=thread_ts,
            user_id=user,
            status=TaskStatus.PENDING
        )
        session.add(task)
        session.commit()
        session.close()
        
        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"タスク {task_id[:8]} を開始しました..."
        )
        
        loop = asyncio.get_event_loop()
        future = await loop.run_in_executor(None, self.task_manager.submit_task, task_id)
        
        asyncio.create_task(self._monitor_task(task_id, channel, thread_ts, client))

    async def _monitor_task(self, task_id: str, channel: str, thread_ts: str, client: AsyncWebClient):
        await asyncio.sleep(5)
        
        session = self.Session()
        task = session.query(Task).filter_by(task_id=task_id).first()
        if task:
            task.status = TaskStatus.AWAITING_CONFIRMATION
            session.commit()
        session.close()
        
        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="タスクの実行中に確認が必要な状況になりました。",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*タスク {task_id[:8]}* の処理を続行しますか？"
                    }
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "承認"
                            },
                            "style": "primary",
                            "action_id": "approve_task",
                            "value": task_id
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "拒否"
                            },
                            "style": "danger",
                            "action_id": "reject_task",
                            "value": task_id
                        }
                    ]
                }
            ]
        )

    async def _handle_approval(
        self, 
        body: dict, 
        client: AsyncWebClient, 
        approved: bool, 
        rejection_reason: Optional[str] = None,
        task_id: Optional[str] = None
    ):
        if not task_id:
            task_id = body["actions"][0]["value"] if "actions" in body else None
        
        if not task_id:
            return
        
        session = self.Session()
        task = session.query(Task).filter_by(task_id=task_id).first()
        
        if not task:
            session.close()
            return
        
        if approved:
            task.status = TaskStatus.APPROVED
            response_text = f"タスク {task_id[:8]} を承認しました。処理を続行します..."
        else:
            task.status = TaskStatus.REJECTED
            task.rejection_reason = rejection_reason
            response_text = f"タスク {task_id[:8]} を拒否しました。\n理由: {rejection_reason}"
        
        session.commit()
        channel = task.channel_id
        thread_ts = task.thread_ts
        session.close()
        
        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=response_text
        )
        
        print(f"Task {task_id} - Approved: {approved}")
        if rejection_reason:
            print(f"Rejection reason: {rejection_reason}")
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, 
            self.task_manager.continue_task, 
            task_id, 
            approved, 
            rejection_reason
        )
        
        await asyncio.sleep(6)
        
        session = self.Session()
        task = session.query(Task).filter_by(task_id=task_id).first()
        if task:
            if approved:
                task.status = TaskStatus.COMPLETED
                await client.chat_postMessage(
                    channel=channel,
                    thread_ts=thread_ts,
                    text=f"✅ タスク {task_id[:8]} が正常に完了しました。"
                )
            session.commit()
        session.close()

    async def start(self):
        await self.socket_mode_handler.start_async()

    def shutdown(self):
        self.task_manager.shutdown()


async def main():
    app_token = os.environ.get("SLACK_APP_TOKEN")
    bot_token = os.environ.get("SLACK_BOT_TOKEN")
    
    if not app_token or not bot_token:
        raise ValueError("SLACK_APP_TOKEN and SLACK_BOT_TOKEN must be set in environment variables")
    
    bot = SlackBot(app_token, bot_token)
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        bot.shutdown()
        print("Bot shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())