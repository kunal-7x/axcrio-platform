"""
auto_lead.pipeline — turn an arbitrary inbound payload into a validated lead.

extract_candidate(payload, mapping) -> {name, phone, email, company, raw}
  Honors an explicit field MAPPING (dot-paths) first; otherwise AUTO-DETECTS common
  field names AND the well-known nested shapes that ad/form platforms send:
    * Meta Lead Ads   -> entry[].changes[].value.field_data[{name, values:[..]}]
    * Google Ads lead -> user_column_data[{column_name, string_value}]
    * generic nested  -> data / lead / fields / answers / payload objects
validate(candidate, rules, norm) -> (ok, reason, phone_normalized)
"""

from __future__ import annotations

import re

NAME_KEYS = ["name", "full_name", "fullname", "full name", "contact_name",
             "lead_name", "your_name", "customer_name"]
FIRST_KEYS = ["first_name", "firstname", "first name", "fname", "given_name"]
LAST_KEYS = ["last_name", "lastname", "last name", "lname", "surname", "family_name"]
PHONE_KEYS = ["phone", "phone_number", "phonenumber", "phone number", "mobile",
              "mobile_number", "tel", "telephone", "contact_number", "contact",
              "whatsapp", "whatsapp_number", "msisdn", "cell", "number"]
EMAIL_KEYS = ["email", "email_address", "emailaddress", "email address", "e-mail",
              "mail", "work_email"]
COMPANY_KEYS = ["company", "company_name", "organization", "organisation",
                "business", "business_name", "org"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _s(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return _s(v[0]) if v else ""
    return str(v).strip()


def _dig(obj, path: str):
    cur = obj
    for k in str(path).split("."):
        if isinstance(cur, list):
            try:
                cur = cur[int(k)]
                continue
            except Exception:  # noqa: BLE001
                return None
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _flatten(payload) -> dict:
    """Best-effort flat dict of lower-cased candidate fields from a varied payload."""
    flat: dict[str, str] = {}

    def absorb(d):
        if isinstance(d, dict):
            for k, v in d.items():
                if isinstance(v, (str, int, float)) and str(k):
                    flat.setdefault(str(k).strip().lower(), v)

    if isinstance(payload, dict):
        absorb(payload)
        # generic nested containers
        for key in ("data", "lead", "fields", "answers", "payload", "contact", "form_response"):
            if isinstance(payload.get(key), dict):
                absorb(payload[key])

    # Meta Lead Ads: field_data anywhere under entry[].changes[].value
    for fd in _find_all(payload, "field_data"):
        if isinstance(fd, list):
            for item in fd:
                if isinstance(item, dict):
                    nm = _s(item.get("name")).lower()
                    val = item.get("values")
                    if nm:
                        flat.setdefault(nm, _s(val))

    # Google Ads lead form: user_column_data[{column_name, string_value}]
    for ucd in _find_all(payload, "user_column_data"):
        if isinstance(ucd, list):
            for item in ucd:
                if isinstance(item, dict):
                    nm = _s(item.get("column_name") or item.get("column_id")).lower().replace(" ", "_")
                    if nm:
                        flat.setdefault(nm, _s(item.get("string_value")))
    return flat


def _find_all(obj, key, _depth=0):
    """Yield every value stored under `key` anywhere in a nested dict/list (bounded)."""
    out = []
    if _depth > 6:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                out.append(v)
            out.extend(_find_all(v, key, _depth + 1))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_find_all(v, key, _depth + 1))
    return out


def _pick(flat: dict, payload, mapping: dict, field: str, keys: list[str]) -> str:
    mapped = (mapping or {}).get(field)
    if mapped:
        v = _dig(payload, mapped)
        if v in (None, "") and isinstance(flat, dict):
            v = flat.get(str(mapped).strip().lower())
        if v not in (None, ""):
            return _s(v)
    for k in keys:
        if k in flat and flat[k] not in (None, ""):
            return _s(flat[k])
    return ""


def extract_candidate(payload, mapping: dict | None = None) -> dict:
    flat = _flatten(payload)
    name = _pick(flat, payload, mapping or {}, "name", NAME_KEYS)
    if not name:
        first = next((_s(flat[k]) for k in FIRST_KEYS if flat.get(k)), "")
        last = next((_s(flat[k]) for k in LAST_KEYS if flat.get(k)), "")
        name = (first + " " + last).strip()
    return {
        "name": name,
        "phone": _pick(flat, payload, mapping or {}, "phone", PHONE_KEYS),
        "email": _pick(flat, payload, mapping or {}, "email", EMAIL_KEYS),
        "company": _pick(flat, payload, mapping or {}, "company", COMPANY_KEYS),
        "raw": payload,
    }


def valid_email(e: str) -> bool:
    return bool(_EMAIL_RE.match((e or "").strip()))


def validate(cand: dict, rules: dict | None, norm) -> tuple[bool, str, str]:
    """(ok, reason, phone_normalized). norm is caller.py's phone normalizer."""
    rules = rules or {}
    require_phone = rules.get("require_phone", True)
    require_email = rules.get("require_email", False)
    valid_phone_only = rules.get("valid_phone_only", True)

    raw_phone = (cand.get("phone") or "").strip()
    phone_norm = norm(raw_phone) if raw_phone else ""

    if require_phone and not raw_phone:
        return False, "missing phone", phone_norm
    if valid_phone_only and raw_phone and not phone_norm:
        return False, "invalid phone number", phone_norm
    if require_email and not valid_email(cand.get("email", "")):
        return False, "missing or invalid email", phone_norm
    if not cand.get("name") and not phone_norm and not cand.get("email"):
        return False, "empty lead (no usable fields)", phone_norm
    return True, "ok", phone_norm
