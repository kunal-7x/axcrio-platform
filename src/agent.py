import os
import re
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, TurnHandlingOptions, llm, stt, tts
from livekit.agents.log import logger
from livekit.plugins import elevenlabs, groq, sarvam, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from knowledge import KnowledgeBase


load_dotenv(".env.local", override=True)
load_dotenv()


AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "voice-assistant")
KNOWLEDGE = KnowledgeBase.from_env()
SALES_BRAIN_PATH = os.getenv(
    "SALES_BRAIN_FILE", "knowledge/groq_real_estate_sales_brain.md"
)


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int_list(name: str, default: list[int]) -> list[int]:
    value = os.getenv(name)
    if not value:
        return default
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def load_sales_brain() -> str:
    if not env_bool("SALES_BRAIN_ENABLED", True):
        return ""

    path = Path(SALES_BRAIN_PATH)
    if not path.exists():
        return ""

    text = path.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"## System prompt\s+```text\s*(.*?)\s*```", text, flags=re.DOTALL)
    max_chars = env_int("SALES_BRAIN_MAX_CHARS", 1200)
    if match:
        text = match.group(1).strip()
    return text[:max_chars].rsplit(".", 1)[0].strip() + "."


SALES_BRAIN = load_sales_brain()


def build_agent_instructions() -> str:
    agent_person_name = os.getenv("AGENT_PERSON_NAME", "Riya").strip()
    company_name = os.getenv("COMPANY_NAME", "Axcrio Enterprises").strip()
    callback_number = os.getenv("SALES_CALLBACK_NUMBER", "").strip()
    base = (
        f"You are {agent_person_name}, an outbound real-estate follow-up caller from {company_name}. "
        "You are calling Indian leads who showed property interest. "
        f"Always introduce yourself as {agent_person_name} from {company_name}; never introduce yourself as Capsy. "
        "Do not open with generic lines like 'main aapki kaise help kar sakti hun'. "
        "The correct opening style is: you are following up on their property enquiry, then ask if this is a good time to talk. "
        "Speak naturally in Hinglish unless the user clearly prefers only English or only Hindi. "
        "Keep replies extremely short, conversational, and easy to hear over a phone call. "
        "Default to one complete sentence, maximum two short sentences. "
        "Ask one question at a time, then stop and wait. "
        "If the caller asks for the best flat, property, area, price, availability, site visit, or booking, "
        "act like a real estate telecaller: qualify budget, preferred area, BHK, timeline, and purpose. "
        "Never invent project names, exact pricing, inventory, offers, legal status, or availability. "
        "If business details are missing, ask the smallest useful follow-up question instead of guessing. "
        "Use provided RAG/business knowledge when it is relevant. "
        "Do not use markdown, emojis, bullets, or long lists. "
        "When collecting names, phone numbers, dates, addresses, or business details, confirm them once."
    )
    if callback_number:
        base += (
            f" Configured sales callback number is {callback_number}. "
        "Use it only if the caller explicitly asks for the callback number; "
        "otherwise collect their details and preferred callback time."
        )
    if not SALES_BRAIN:
        return base
    return (
        f"{base}\n\n"
        "Real-estate sales brain to follow during calls:\n"
        f"{SALES_BRAIN}"
    )


def build_stt() -> stt.STT:
    provider = os.getenv("STT_PROVIDER", "elevenlabs").strip().lower()

    if provider == "elevenlabs":
        server_vad = None
        if env_bool("ELEVEN_STT_SERVER_VAD", True):
            server_vad = {
                "vad_silence_threshold_secs": env_float(
                    "ELEVEN_STT_VAD_SILENCE_THRESHOLD_SECS", 0.45
                ),
                "vad_threshold": env_float("ELEVEN_STT_VAD_THRESHOLD", 0.35),
                "min_speech_duration_ms": env_int("ELEVEN_STT_MIN_SPEECH_DURATION_MS", 120),
                "min_silence_duration_ms": env_int("ELEVEN_STT_MIN_SILENCE_DURATION_MS", 450),
            }

        return elevenlabs.STT(
            api_key=os.getenv("ELEVEN_API_KEY"),
            model_id=os.getenv("ELEVEN_STT_MODEL", "scribe_v2_realtime"),
            language_code=os.getenv("ELEVEN_STT_LANGUAGE", "hi"),
            sample_rate=int(os.getenv("ELEVEN_STT_SAMPLE_RATE", "16000")),
            server_vad=server_vad,
        )

    if provider == "sarvam":
        return sarvam.STT(
            api_key=os.getenv("SARVAM_API_KEY"),
            model=os.getenv("SARVAM_STT_MODEL", "saarika:v2.5"),
            language=os.getenv("SARVAM_STT_LANGUAGE", "hi-IN"),
            sample_rate=int(os.getenv("SARVAM_STT_SAMPLE_RATE", "16000")),
            high_vad_sensitivity=env_bool("SARVAM_STT_HIGH_VAD_SENSITIVITY", True),
            prompt="The caller may speak Hinglish, Hindi, and Indian English in the same sentence.",
        )

    raise ValueError(f"Unsupported STT_PROVIDER={provider!r}. Use 'elevenlabs' or 'sarvam'.")


def build_tts() -> tts.TTS:
    provider = os.getenv("TTS_PROVIDER", "sarvam").strip().lower()

    if provider == "elevenlabs":
        return elevenlabs.TTS(
            api_key=os.getenv("ELEVEN_API_KEY"),
            voice_id=os.getenv("ELEVEN_TTS_VOICE_ID", "l7kNoIfnJKPg7779LI2t"),
            model=os.getenv("ELEVEN_TTS_MODEL", "eleven_flash_v2_5"),
            language=os.getenv("ELEVEN_TTS_LANGUAGE", "hi"),
            auto_mode=env_bool("ELEVEN_TTS_AUTO_MODE", True),
            streaming_latency=env_int("ELEVEN_TTS_STREAMING_LATENCY", 1),
            chunk_length_schedule=env_int_list("ELEVEN_TTS_CHUNK_LENGTH_SCHEDULE", [50, 80, 120]),
            encoding=os.getenv("ELEVEN_TTS_ENCODING", "mp3_22050_32"),
            sync_alignment=env_bool("ELEVEN_TTS_SYNC_ALIGNMENT", False),
            apply_text_normalization=os.getenv("ELEVEN_TTS_TEXT_NORMALIZATION", "off"),
            apply_language_text_normalization=env_bool(
                "ELEVEN_TTS_LANGUAGE_TEXT_NORMALIZATION", False
            ),
            enable_logging=env_bool("ELEVEN_TTS_ENABLE_LOGGING", False),
        )

    if provider == "sarvam":
        return sarvam.TTS(
            api_key=os.getenv("SARVAM_API_KEY"),
            model=os.getenv("SARVAM_TTS_MODEL", "bulbul:v3"),
            target_language_code=os.getenv("SARVAM_TTS_LANGUAGE", "hi-IN"),
            speaker=os.getenv("SARVAM_TTS_SPEAKER", "shubh"),
            pace=float(os.getenv("SARVAM_TTS_PACE", "1.05")),
            speech_sample_rate=int(os.getenv("SARVAM_TTS_SAMPLE_RATE", "24000")),
            min_buffer_size=env_int("SARVAM_TTS_MIN_BUFFER_SIZE", 30),
            max_chunk_length=env_int("SARVAM_TTS_MAX_CHUNK_LENGTH", 80),
            enable_preprocessing=env_bool("SARVAM_TTS_ENABLE_PREPROCESSING", False),
            output_audio_bitrate=os.getenv("SARVAM_TTS_OUTPUT_AUDIO_BITRATE", "32k"),
            enable_cached_responses=env_bool("SARVAM_TTS_ENABLE_CACHED_RESPONSES", True),
            output_audio_codec=os.getenv("SARVAM_TTS_CODEC", "mp3"),
        )

    raise ValueError(f"Unsupported TTS_PROVIDER={provider!r}. Use 'elevenlabs' or 'sarvam'.")


class CapsyAssistant(Agent):
    def __init__(self) -> None:
        self.knowledge = KNOWLEDGE
        super().__init__(
            instructions=build_agent_instructions()
        )

    async def llm_node(self, chat_ctx: llm.ChatContext, tools, model_settings):
        latest_user_text = ""
        for message in reversed(chat_ctx.messages()):
            if message.role == "user" and message.text_content:
                latest_user_text = message.text_content
                break

        knowledge_context = self.knowledge.context_for(latest_user_text)
        if knowledge_context:
            chat_ctx = chat_ctx.copy()
            chat_ctx.add_message(role="system", content=knowledge_context)
            logger.debug(
                "rag context injected",
                extra={
                    "query": latest_user_text[:160],
                    "context_chars": len(knowledge_context),
                },
            )
        else:
            logger.debug(
                "rag context not found",
                extra={"query": latest_user_text[:160], "chunks": len(self.knowledge.chunks)},
            )

        async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
            yield chunk


server = AgentServer()


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: agents.JobContext) -> None:
    session = AgentSession(
        stt=build_stt(),
        llm=groq.LLM(
            model=os.getenv("GROQ_LLM_MODEL", "llama-3.1-8b-instant"),
            api_key=os.getenv("GROQ_API_KEY"),
            temperature=env_float("GROQ_LLM_TEMPERATURE", 0.25),
            max_completion_tokens=env_int("GROQ_LLM_MAX_COMPLETION_TOKENS", 48),
        ),
        tts=build_tts(),
        vad=silero.VAD.load(),
        aec_warmup_duration=env_float("AGENT_AEC_WARMUP_DURATION", 0.0),
        min_interruption_duration=env_float("AGENT_MIN_INTERRUPTION_DURATION", 0.15),
        min_interruption_words=env_int("AGENT_MIN_INTERRUPTION_WORDS", 1),
        false_interruption_timeout=env_float("AGENT_FALSE_INTERRUPTION_TIMEOUT", 0.5),
        resume_false_interruption=env_bool("AGENT_RESUME_FALSE_INTERRUPTION", False),
        turn_handling=TurnHandlingOptions(
            endpointing={
                "min_delay": env_float("AGENT_MIN_ENDPOINTING_DELAY", 0.1),
                "max_delay": env_float("AGENT_MAX_ENDPOINTING_DELAY", 0.45),
            },
            preemptive_generation={"enabled": True, "preemptive_tts": True},
            turn_detection=MultilingualModel(),
        ),
    )

    await session.start(room=ctx.room, agent=CapsyAssistant())
    await session.say(
        os.getenv("AGENT_GREETING_TEXT", "Namaste, main Capsy. Kaise madad karun?"),
        allow_interruptions=True,
    )


if __name__ == "__main__":
    agents.cli.run_app(server)
