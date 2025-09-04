import logging

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RoomInputOptions,
    WorkerOptions,
    cli,
    stt,
    RunContext,
)
from livekit.agents.llm import function_tool
from livekit.plugins import deepgram, noise_cancellation, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents import metrics, MetricsCollectedEvent
from livekit.agents import mcp

logger = logging.getLogger("agent")

load_dotenv(".env.local")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""
            You are a hilariously funny voice AI assistant.
            You are also a bit sarcastic.
            Assist the user, but don't be too helpful.
            """,
            mcp_servers=[
                mcp.MCPServerHTTP(url="https://shayne.app/sse"),
            ],
        )
    
    @function_tool
    async def lookup_weather(self, context: RunContext, location: str):
        """Use this tool to look up current weather information in the given location.

        If the location is not supported by the weather service, the tool will indicate this. You must tell the user the location's weather is unavailable.

        Args:
            location: The location to look up weather information for (e.g. city name)
        """

        logger.info(f"Looking up weather for {location}")

        return "sunny with a temperature of 70 degrees."

async def entrypoint(ctx: JobContext):
    vad = silero.VAD.load()
    
    session = AgentSession(
        llm=openai.LLM(model="gpt-4o-mini"),
        stt=stt.FallbackAdapter([
            deepgram.STT(model="nova-3", language="multi"),
            stt.StreamAdapter(stt=openai.STT(model="gpt-4o-transcribe"), vad=vad)
        ]),
        tts=openai.TTS(voice="ash"),
        vad=vad,
        turn_detection=MultilingualModel(),
        preemptive_generation=True,
    )
    
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)
    
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
