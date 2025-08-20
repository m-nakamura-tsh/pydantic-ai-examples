from pydantic_ai import Agent
from pydantic_ai.agent import AgentRunResult
from pydantic_ai.messages import ModelMessage
from pydantic_ai.mcp import MCPServerStdio
import os
import asyncio
from rich.prompt import Prompt
import dotenv

dotenv.load_dotenv()

ESA_API_KEY = os.environ["ESA_API_KEY"]

server = MCPServerStdio(
    "npx",
    args=[
        "-y",
        "esa-mcp-server@latest",
    ],
    env={"ESA_API_KEY": ESA_API_KEY, "DEFAULT_ESA_TEAM": "tsh-world"},
)
agent = Agent("openai:gpt-4o", system_prompt="あなたは、ドキュメントの編集に長けた、優秀なアシスタントです。", toolsets=[server])


async def summarize_content(request_message: str) -> AgentRunResult:
    async with agent:
        result = await agent.run(request_message)
    print(result.output)
    return result


async def arrange_summary(
    request_message: str, message_history: list[ModelMessage]
) -> AgentRunResult:
    async with agent:
        result = await agent.run(request_message, message_history=message_history)
    print(result.output)
    return result


async def main():
    # 要約のコンテンツを取得する
    result = await summarize_content(
        "記事 https://tsh-world.esa.io/posts/5616 の内容を要約して下さい。"
    )

    # 要約の内容を修正する
    fix_summary = Prompt.ask("修正しますか？: ", choices=["yes", "no"])
    if fix_summary:
        arrange_request = Prompt.ask("修正内容を教えてください: ")
        result = await arrange_summary(
            arrange_request, message_history=result.all_messages()
        )


if __name__ == "__main__":
    asyncio.run(main())
