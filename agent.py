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
    llm,
    tts,
    RunContext,
)
from livekit.agents.llm import function_tool
from livekit.plugins import deepgram, noise_cancellation, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents import metrics, MetricsCollectedEvent, AgentStateChangedEvent
from livekit.agents.telemetry import set_tracer_provider
import os
import base64
from livekit.agents import mcp
import aiohttp


logger = logging.getLogger("agent")

load_dotenv(".env.local")

def setup_langfuse(
    host: str | None = None, public_key: str | None = None, secret_key: str | None = None
):
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    public_key = public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = secret_key or os.getenv("LANGFUSE_SECRET_KEY")
    host = host or os.getenv("LANGFUSE_HOST")

    if not public_key or not secret_key or not host:
        raise ValueError("LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and LANGFUSE_HOST must be set")

    langfuse_auth = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = f"{host.rstrip('/')}/api/public/otel"
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {langfuse_auth}"

    trace_provider = TracerProvider()
    trace_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    set_tracer_provider(trace_provider)


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

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"http://shayne.app/weather?location={location}") as response:
                    if response.status == 200:
                        data = await response.json()
                        condition = data.get("condition", "unknown")
                        temperature = data.get("temperature", "unknown")
                        unit = data.get("unit", "degrees")
                        return f"{condition} with a temperature of {temperature} {unit}"
                    else:
                        logger.error(f"Weather API returned status {response.status}")
                        return "Weather information is currently unavailable for this location."
        except Exception as e:
            logger.error(f"Error fetching weather: {e}")
            return "Weather service is temporarily unavailable."


async def entrypoint(ctx: JobContext):
    setup_langfuse()
    
    vad = silero.VAD.load()

    session = AgentSession(
        llm=llm.FallbackAdapter(
            [
                openai.LLM(model="gpt-4.1"),
                openai.LLM(model="gpt-4o-mini"),
            ]
        ),
        stt=stt.FallbackAdapter(
            [
                deepgram.STT(model="nova-3", language="multi"),
                stt.StreamAdapter(stt=openai.STT(model="gpt-4o-transcribe"), vad=vad),
            ]
        ),
        tts=tts.FallbackAdapter(
            [
                openai.TTS(voice="ash"),
                deepgram.TTS(),
            ]
        ),
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
