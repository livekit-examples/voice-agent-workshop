import logging

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RoomInputOptions,
    WorkerOptions,
    cli,
    stt
)
from livekit.plugins import deepgram, noise_cancellation, openai, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="You are a helpful voice AI assistant.",
        )

async def entrypoint(ctx: JobContext):
    vad = silero.VAD.load()
    
    session = AgentSession(
        llm=openai.LLM(model="gpt-4o-mini"),
        stt=stt.FallbackAdapter([
            deepgram.STT(model="nova-3", language="multi"),
            stt.StreamAdapter(stt=openai.STT(model="gpt-4o-transcribe"), vad=vad)
        ]),
        tts=openai.TTS(voice="marin"),
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
