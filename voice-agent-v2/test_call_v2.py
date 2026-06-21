#!/usr/bin/env python3
"""One-shot REAL test call routed to capsy-v2 (ROUND-10 clean brain).

Dials the given E.164 number over the live SIP trunk and dispatches the NEW agent
(capsy-v2) to that room — the live earner (capsy) is never involved. Mirrors caller.py's
own dial+dispatch (create_room -> create_dispatch(agent_name=capsy-v2) -> create_sip_participant).

  /opt/capsy-agent/.venv/bin/python /opt/famit-agent-v2/test_call_v2.py +91XXXXXXXXXX [campaign_id] [lead_name]

campaign_id empty -> the default clean Godrej real-estate brain. lead_name -> greets by name.
"""
import asyncio
import json
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv("/opt/famit-agent-v2/.env")
load_dotenv("/opt/famit-agent/.env")
from livekit import api  # noqa: E402

LK_URL = os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880")
LK_KEY = os.getenv("LIVEKIT_API_KEY", "")
LK_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
TRUNK = os.getenv("LIVEKIT_SIP_TRUNK_ID", "ST_fmtVmNJmpzKa")
AGENT = "capsy-v2"


async def main() -> int:
    num = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not num.startswith("+") or len(num) < 8:
        print("usage: test_call_v2.py +<E164 number> [campaign_id] [lead_name]")
        return 2
    cid = sys.argv[2] if len(sys.argv) > 2 else ""
    lead = sys.argv[3] if len(sys.argv) > 3 else ""
    if not (LK_KEY and LK_SECRET):
        print("ERROR: LIVEKIT_API_KEY / LIVEKIT_API_SECRET not found in env")
        return 3
    room = f"famit-{num[1:]}-{uuid.uuid4().hex[:6]}"
    md = json.dumps({"campaign_id": cid, "lead_name": lead})
    lk = api.LiveKitAPI(url=LK_URL, api_key=LK_KEY, api_secret=LK_SECRET)
    try:
        await lk.room.create_room(api.CreateRoomRequest(
            name=room, empty_timeout=300, departure_timeout=20))
        await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(
            room=room, agent_name=AGENT, metadata=md))
        resp = await lk.sip.create_sip_participant(api.CreateSIPParticipantRequest(
            sip_trunk_id=TRUNK, sip_call_to=num, room_name=room,
            participant_identity=f"phone-{num}", participant_name=(lead or num),
            wait_until_answered=False))
        print("DISPATCHED capsy-v2 OK  room=%s  num=%s  sip_call_id=%s"
              % (room, num, (getattr(resp, "sip_call_id", "") or "")))
        return 0
    except Exception as exc:  # noqa: BLE001
        print("DISPATCH FAILED: %r" % (exc,))
        return 1
    finally:
        await lk.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
