from pydantic_ai import Agent
from pydantic_graph import End
from pydantic_ai.tools import RunContext
import asyncio
from dataclasses import dataclass
from datetime import date
from devtools import debug


@dataclass
class WeatherService:
    async def get_forecast(self, location: str, forecast_date: date) -> str:
        # In real code: call weather API, DB queries, etc.
        return f'The forecast in {location} on {forecast_date} is 24°C and sunny.'

    async def get_historic_weather(self, location: str, forecast_date: date) -> str:
        # In real code: call a historical weather API or DB
        return f'The weather in {location} on {forecast_date} was 18°C and partly cloudy.'

weather_agent = Agent[WeatherService, str](
    'openai:gpt-4o',
    deps_type=WeatherService,
    output_type=str,  # We'll produce a final answer as plain text
    system_prompt='Providing a weather forecast at the locations the user provides.',
)


@weather_agent.tool
async def weather_forecast(
    ctx: RunContext[WeatherService],
    location: str,
    forecast_date: date,
) -> str:
    # ctx.messages にアクセスできる。
    debug(ctx)
    if forecast_date >= date.today():
        return await ctx.deps.get_forecast(location, forecast_date)
    else:
        return await ctx.deps.get_historic_weather(location, forecast_date)


async def main():
    async with weather_agent.iter('What will the weather be like in Paris on Tuesday?', deps=WeatherService()) as agent_run:
        node = agent_run.next_node  

        all_nodes = [node]

        # Drive the iteration manually:
        while not isinstance(node, End):  
            debug(node)
            print(f"{type(agent_run.ctx)=}")
            # このctxは、toolなどでアクセスできるRunContextではない。.messages には、ctx.status.message_history などでアクセスする。
            node = await agent_run.next(node)  
            all_nodes.append(node)  

        print(all_nodes)

if __name__=="__main__":
    asyncio.run(main())
