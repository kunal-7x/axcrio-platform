"""bridge.py — scheduler→LiveKit dial bridge (FastAPI).

The product's scheduler POSTs to {TELEPHONY_URL}/v1/calls to place a call. This bridge
implements that exact contract but places the call through our working LiveKit agent
instead of the old telephony-adapter. It runs ON the famit-livekit droplet (where LiveKit
is reachable at localhost:7880) and is firewalled to the product droplet only.

Contract (from services/scheduler/internal/dispatcher/dispatcher.go):
  POST /v1/calls  {session_id, tenant_id, campaign_id, lead_id, project_id,
                   from_number, to_number, callback_url, max_duration, machine_detection}
  -> 200 {provider_call_id, session_id, provider, status}   (provider_call_id must be non-empty)

The call is placed in the background so we return fast (scheduler isn't blocked).
"""
from __future__ import annotations

import asyncio
import os
import re
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from google.protobuf.duration_pb2 import Duration
from livekit import api

load_dotenv("/opt/famit-agent/.env")

TRUNK = os.getenv("LIVEKIT_SIP_TRUNK_ID", "ST_fmtVmNJmpzKa")
AGENT = os.getenv("LIVEKIT_AGENT_NAME", "capsy")
LK_URL = os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880")
LK_KEY = os.environ["LIVEKIT_API_KEY"]
LK_SECRET = os.environ["LIVEKIT_API_SECRET"]

app = FastAPI()


def _normalize(num: str) -> str:
    d = re.sub(r"\D", "", num or "")
    if len(d) == 10:
        d = "91" + d
    return "+" + d if d else ""


async def _place(to_number: str, room: str) -> None:
    """Background: dispatch the agent + dial the lead via the Vobiz SIP trunk."""
    lk = api.LiveKitAPI(url=LK_URL, api_key=LK_KEY, api_secret=LK_SECRET)
    try:
        await lk.room.create_room(api.CreateRoomRequest(name=room, empty_timeout=300, departure_timeout=20))
        await lk.agent_dispatch.create_dispatch(api.CreateAgentDispatchRequest(room=room, agent_name=AGENT))
        await lk.sip.create_sip_participant(api.CreateSIPParticipantRequest(
            sip_trunk_id=TRUNK, sip_call_to=to_number, room_name=room,
            participant_identity=f"phone-{to_number}", participant_name=to_number,
            wait_until_answered=False, ringing_timeout=Duration(seconds=50)))
    except Exception as exc:  # noqa: BLE001
        print(f"[bridge] place failed to={to_number} room={room} err={exc!r}")
    finally:
        await lk.aclose()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "agent": AGENT, "trunk": TRUNK}


@app.post("/v1/calls")
async def create_call(req: Request) -> dict:
    body = await req.json()
    to_number = _normalize(body.get("to_number", ""))
    session_id = body.get("session_id") or uuid.uuid4().hex
    if not to_number:
        return {"provider_call_id": session_id, "session_id": session_id,
                "provider": "livekit", "status": "rejected", "error": "no to_number"}
    digits = to_number[1:]
    room = f"famit-{digits}-{uuid.uuid4().hex[:6]}"
    provider_call_id = f"lk_{uuid.uuid4().hex[:16]}"
    # fire-and-forget so the scheduler gets a fast response
    asyncio.create_task(_place(to_number, room))
    print(f"[bridge] call queued to={to_number} room={room} pcid={provider_call_id}")
    return {"provider_call_id": provider_call_id, "session_id": session_id,
            "provider": "livekit", "status": "queued"}
