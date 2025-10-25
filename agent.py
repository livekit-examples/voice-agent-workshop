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
        )


async def entrypoint(ctx: JobContext):
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
