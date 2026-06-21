"""Offline probe: does firewall.check_pin work in a FRESH process (the aim_voice_agent runtime),
with only /opt/famit-agent/.env loaded, WITHOUT caller.py calling firewall.init()?
Prints PASS/FAIL booleans only — never the raw PIN."""
import os
from dotenv import load_dotenv
load_dotenv("/opt/famit-agent/.env")
import inspect
import firewall

print("available_pre_init:", firewall.available())
print("has_check_pin:", hasattr(firewall, "check_pin"))
print("init_sig:", str(inspect.signature(firewall.init)))
print("FIREWALL_SECRET_set:", bool(os.getenv("FIREWALL_SECRET")))
print("FIREWALL_PIN_FILE_env:", os.getenv("FIREWALL_PIN_FILE"))
print("FIREWALL_STEPUP_SECRET_set:", bool(os.getenv("FIREWALL_STEPUP_SECRET")))

from ai_manager import firewall_bridge as fb
print("bridge_check_pin_PRE_init:", fb.check_pin("admin", "4827"))
print("bridge_has_pin_admin:", fb.has_pin("admin"))

# Try explicit init the way caller.py would, then re-test
from pathlib import Path
secret = os.getenv("FIREWALL_SECRET") or os.getenv("FIREWALL_STEPUP_SECRET") or os.getenv("JWT_SECRET") or "x"
pin_file = os.getenv("FIREWALL_PIN_FILE") or "/opt/famit-agent/var/pins.json"
try:
    firewall.init(secret, Path(pin_file))
    print("post_init_available:", firewall.available())
    print("bridge_check_pin_POST_init_correct:", fb.check_pin("admin", "4827"))
    print("bridge_check_pin_POST_init_wrong:", fb.check_pin("admin", "0000"))
except Exception as e:
    print("init_raised:", repr(e))
