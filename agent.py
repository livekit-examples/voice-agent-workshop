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
)
from livekit.plugins import deepgram, noise_cancellation, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.agents import metrics, MetricsCollectedEvent, AgentStateChangedEvent
from livekit.agents.telemetry import set_tracer_provider
import os
import base64

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
        )


async def entrypoint(ctx: JobContext):
    setup_langfuse()
    
    vad = silero.VAD.load()

    session = AgentSession(
        llm=llm.FallbackAdapter(
            [
                "openai/gpt-4.1-mini",
                "google/gemini-2.5-flash",
            ]
        ),
        stt=stt.FallbackAdapter(
           [
               "deepgram/nova-3",
               "assemblyai/universal-streaming"
           ]
        ),
        tts=tts.FallbackAdapter(
           [
               "cartesia/sonic-2:a167e0f3-df7e-4d52-a9c3-f949145efdab",
               "inworld/inworld-tts-1",
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
