"""Place an outbound call. Usage: place_call.py <number>  (10-digit or +91...)."""
import asyncio
import os
import re
import sys
import uuid

from dotenv import load_dotenv
from google.protobuf.duration_pb2 import Duration
from livekit import api

load_dotenv("/opt/famit-agent/.env")

TRUNK = os.getenv("LIVEKIT_SIP_TRUNK_ID", "ST_fmtVmNJmpzKa")
AGENT = os.getenv("LIVEKIT_AGENT_NAME", "capsy")


def normalize(num: str) -> str:
    d = re.sub(r"\D", "", num)
    if len(d) == 10:
        d = "91" + d
    return "+" + d


async def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: place_call.py <number>")
    dest = normalize(sys.argv[1])
    digits = dest[1:]
    lk = api.LiveKitAPI(
        url=os.environ["LIVEKIT_URL"],
        api_key=os.environ["LIVEKIT_API_KEY"],
        api_secret=os.environ["LIVEKIT_API_SECRET"],
    )
    room = f"famit-{digits}-{uuid.uuid4().hex[:6]}"
    await lk.room.create_room(api.CreateRoomRequest(name=room, empty_timeout=300, departure_timeout=20))
    await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(room=room, agent_name=AGENT))
    print(f"calling {dest}  room={room}")
    try:
        p = await lk.sip.create_sip_participant(api.CreateSIPParticipantRequest(
            sip_trunk_id=TRUNK, sip_call_to=dest, room_name=room,
            participant_identity=f"phone-{dest}", participant_name=dest,
            wait_until_answered=True, ringing_timeout=Duration(seconds=50)))
        print("ANSWERED", p.participant_id)
    except Exception as e:  # noqa: BLE001
        print("CALL_ERROR", repr(e)[:240])
    await lk.aclose()


if __name__ == "__main__":
    asyncio.run(main())
