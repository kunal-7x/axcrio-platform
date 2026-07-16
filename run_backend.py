#!/usr/bin/env python3
"""Local launcher for the Famit backend (caller.py) — portable (repo-relative).
Sets a local FAMIT_VAR so admin/tenants/secret persist, loads droplet_work/.env
(caller.py only auto-loads the box path), serves the FastAPI app on :8091.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DW = os.path.join(ROOT, "droplet_work")

os.environ.setdefault("FAMIT_VAR", os.path.join(ROOT, "famit-var"))
os.environ["LIVEKIT_AGENT_NAME"] = "famit-local"   # unique name (avoid other LiveKit workers)
os.makedirs(os.environ["FAMIT_VAR"], exist_ok=True)
os.chdir(DW)
sys.path.insert(0, DW)

from dotenv import load_dotenv
load_dotenv(os.path.join(DW, ".env"))

import uvicorn
uvicorn.run("caller:app", host="127.0.0.1", port=8091, log_level="warning")
