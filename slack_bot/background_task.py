from esa_summarizing import summarize_content, arrange_summary
from devtools import debug
import logfire

logfire.configure()  
logfire.instrument_pydantic_ai()
logfire.instrument_httpx(capture_all=True)

class TaskManager:
    def __init__(self, slack_bot):
        self.slack_bot = slack_bot
    
    async def do_summarize(self, task_id:str, message:str = "記事 https://tsh-world.esa.io/posts/5616 の内容を要約して下さい。"):
        # LLMによる要約を実行
        print("in do_summarize..")
        result = await summarize_content(request_message=message)
        debug(result)
        #breakpoint()
        self.slack_bot.task_repository.update_model_messages(task_id, messages=result.all_messages())
        # slack_bot をコールバックする
        print("\tcallback request_feedback_to_user")
        await self.slack_bot.request_feedback_to_user(task_id=task_id, message=result.output)
        return
    
    async def do_feedback(self, task_id:str, message:str):
        print("in do_feedback..")
        message_history = self.slack_bot.task_repository.get_model_messages(task_id)
        debug(message_history)
        # LLMによる要約を実行
        if message_history:
            result = await arrange_summary(request_message=message, message_history=message_history)
            # slack_bot をコールバックする
            print("\tcallback request_feedback_to_user")
            await self.slack_bot.request_feedback_to_user(task_id=task_id, message=result.output)
            return
        else:
            return
