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
from livekit.agents import metrics, MetricsCollectedEvent, AgentStateChangedEvent
from livekit.agents import mcp
from livekit.agents import AgentTask

logger = logging.getLogger("agent")

load_dotenv(".env.local")


class CollectConsent(AgentTask[bool]):
    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="""
            Ask for recording consent and get a clear yes or no answer.
            Be polite and professional.
            """,
            chat_ctx=chat_ctx,
        )

    async def on_enter(self) -> None:
        await self.session.generate_reply(instructions="""
                                          Brief ask for permission to record the call for quality assurance and training purposes.
                                          Make it clear that they can decline.
                                          """)

    @function_tool
    async def consent_given(self) -> None:
        """Use this when the user gives consent to record."""
        self.complete(True)

    @function_tool
    async def consent_denied(self) -> None:
        """Use this when the user denies consent to record."""
        self.complete(False)

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
    
    async def on_enter(self) -> None:
        if await CollectConsent(chat_ctx=self.chat_ctx):
            logger.info("User gave consent to record.")
            await self.session.generate_reply(instructions="Thank the user for their consent then offer your assistance.")
        else:
            logger.info("User did not give consent to record.")
            await self.session.generate_reply(instructions="Let the user know that the call will not be recorded, then offer your assistance.")
    
    @function_tool
    async def lookup_weather(self, context: RunContext, location: str):
        """Use this tool to look up current weather information in the given location.

        If the location is not supported by the weather service, the tool will indicate this. You must tell the user the location's weather is unavailable.

        Args:
            location: The location to look up weather information for (e.g. city name)
        """

        logger.info(f"Looking up weather for {location}")

        return "sunny with a temperature of 70 degrees."
    
    @function_tool
    async def escalate_to_manager(self, context: RunContext):
        """Use this tool to escalate the call to the manager, upon user request."""
        return Manager(chat_ctx=self.chat_ctx), "Escalating to manager..."


class Manager(Agent):
    def __init__(self, chat_ctx=None):
        super().__init__(
            instructions="""You are a manager for a team of helpful voice AI assistants. 
            A customer has been escalated to you.
            Provide your assistant and be professional.
            """,
            tts=openai.TTS(voice="coral"),
            chat_ctx=chat_ctx,
        )
    
    async def on_enter(self) -> None:
        await self.session.generate_reply(instructions="Introduce yourself as the manager and offer your assistance.")

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
    last_eou_metrics: metrics.EOUMetrics | None = None

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        nonlocal last_eou_metrics
        if ev.metrics.type == "eou_metrics":
            last_eou_metrics = ev.metrics
        
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)
    
    @session.on("agent_state_changed")
    def _on_agent_state_changed(ev: AgentStateChangedEvent):
        if (
            ev.new_state == "speaking"
            and last_eou_metrics
            and last_eou_metrics.speech_id == session.current_speech.id
        ):
            logger.info(
                f"Agent response - Time to first audio frame: {ev.created_at - last_eou_metrics.last_speaking_time}"
            )
    
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
