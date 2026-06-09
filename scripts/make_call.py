import asyncio
import os
import sys
import uuid

from aiohttp import ClientConnectorError
from dotenv import load_dotenv
from google.protobuf.duration_pb2 import Duration
from livekit import api as livekit_api
from livekit.api.twirp_client import TwirpError


load_dotenv(".env.local", override=True)
load_dotenv()


AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "voice-assistant")
CALL_RINGING_TIMEOUT_SECONDS = int(os.getenv("CALL_RINGING_TIMEOUT_SECONDS", "45"))


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def require_sip_trunk_id() -> str:
    value = require_env("LIVEKIT_SIP_TRUNK_ID")
    if value.startswith("sip:") or "@" in value:
        raise RuntimeError(
            "LIVEKIT_SIP_TRUNK_ID must be the outbound trunk ID returned by "
            "scripts/setup_vobiz_trunk.py, not a SIP URI or Vobiz registrar address."
        )
    return value


async def prepare_room(lk: livekit_api.LiveKitAPI, room_name: str) -> None:
    await lk.room.create_room(
        livekit_api.CreateRoomRequest(
            name=room_name,
            empty_timeout=300,
            departure_timeout=30,
        )
    )

    dispatch = await lk.agent_dispatch.create_dispatch(
        livekit_api.CreateAgentDispatchRequest(
            room=room_name,
            agent_name=AGENT_NAME,
        )
    )
    print(f"agent_dispatch_id={dispatch.id}")


async def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: uv run python scripts/make_call.py +91XXXXXXXXXX [room-name]")

    destination = sys.argv[1]
    room_name = sys.argv[2] if len(sys.argv) > 2 else f"call-{uuid.uuid4().hex[:8]}"

    lk = livekit_api.LiveKitAPI(
        url=require_env("LIVEKIT_URL"),
        api_key=require_env("LIVEKIT_API_KEY"),
        api_secret=require_env("LIVEKIT_API_SECRET"),
    )

    try:
        await prepare_room(lk, room_name)
        participant = await lk.sip.create_sip_participant(
            livekit_api.CreateSIPParticipantRequest(
                sip_trunk_id=require_sip_trunk_id(),
                sip_call_to=destination,
                room_name=room_name,
                participant_identity=f"phone-{destination}",
                participant_name=destination,
                wait_until_answered=True,
                ringing_timeout=Duration(seconds=CALL_RINGING_TIMEOUT_SECONDS),
            )
        )
        print(f"room_name={room_name}")
        print(f"participant_id={participant.participant_id}")
        print("call_status=answered")
    except ClientConnectorError as exc:
        raise RuntimeError(
            f"Cannot connect to LiveKit at {require_env('LIVEKIT_URL')}. "
            "Start your local LiveKit server first with `livekit-server --dev`, "
            "or update LIVEKIT_URL to a reachable LiveKit server."
        ) from exc
    except TwirpError as exc:
        message = str(exc)
        sip_status = getattr(exc, "metadata", {}).get("sip_status")
        sip_status_code = getattr(exc, "metadata", {}).get("sip_status_code")
        if sip_status_code == "486" or sip_status == "Busy Here":
            raise RuntimeError(
                "Outbound call was rejected as busy by the destination/carrier "
                "(SIP 486 Busy Here). Hang up the previous call or wait a few seconds, then retry."
            ) from exc
        if exc.status == 408 or "0 intermediate responses" in message:
            raise RuntimeError(
                "Outbound SIP invite timed out before Vobiz returned any SIP response. "
                "The phone will not ring until the SIP trunk/network path is reachable. "
                "Check that VOBIZ_SIP_DOMAIN is the outbound SIP server, Vobiz allows this "
                "server's public IP, outbound calling is enabled for the trunk, and your "
                "self-hosted machine exposes SIP 5060 TCP/UDP plus RTP UDP ports to the internet. "
                "For production, run LiveKit/SIP on a VPS with a public static IP."
            ) from exc
        raise
    finally:
        await lk.aclose()


if __name__ == "__main__":
    asyncio.run(main())
