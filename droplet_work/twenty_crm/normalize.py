"""
twenty_crm.normalize — translate between Twenty's composite-field records and the
flat shapes the Haptica panel consumes.

Twenty stores "composite" fields as nested objects (FullName, Emails, Phones,
Links, Currency, Address). The panel wants flat scalars (``name``, ``email``,
``phone``, ``amount`` …). These helpers convert both directions and are defensive
about field drift between Twenty versions (e.g. ``body`` vs ``bodyV2``,
``annualRecurringRevenue`` vs ``annualRevenue``) and about relations only being
present when the request used ``depth >= 1``.
"""

from __future__ import annotations

from typing import Any

_MICROS = 1_000_000


# ── readers (Twenty record -> flat dict) ─────────────────────────────────────
def _g(d: Any, *path, default=None):
    """Safe nested get: _g(rec, 'name', 'firstName')."""
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    return cur if cur is not None else default


def _full_name(rec: dict) -> str:
    fn = _g(rec, "name", "firstName", default="") or ""
    ln = _g(rec, "name", "lastName", default="") or ""
    return (f"{fn} {ln}").strip()


def _money_major(rec: dict, field: str = "amount") -> float | None:
    micros = _g(rec, field, "amountMicros")
    if micros is None:
        return None
    try:
        return round(float(micros) / _MICROS, 2)
    except Exception:  # noqa: BLE001
        return None


def person_out(rec: dict) -> dict:
    """Twenty person record -> flat person."""
    company = rec.get("company") if isinstance(rec.get("company"), dict) else {}
    return {
        "id": rec.get("id"),
        "name": _full_name(rec) or "Unknown",
        "firstName": _g(rec, "name", "firstName", default=""),
        "lastName": _g(rec, "name", "lastName", default=""),
        "email": _g(rec, "emails", "primaryEmail", default="") or "",
        "phone": _g(rec, "phones", "primaryPhoneNumber", default="") or "",
        "jobTitle": rec.get("jobTitle") or "",
        "city": rec.get("city") or "",
        "avatarUrl": rec.get("avatarUrl") or "",
        "companyId": rec.get("companyId") or (company.get("id") if company else None),
        "companyName": company.get("name") if company else None,
        "createdAt": rec.get("createdAt"),
        "updatedAt": rec.get("updatedAt"),
    }


def company_out(rec: dict) -> dict:
    """Twenty company record -> flat company."""
    people = rec.get("people")
    opps = rec.get("opportunities")
    return {
        "id": rec.get("id"),
        "name": rec.get("name") or "Untitled",
        "domain": _g(rec, "domainName", "primaryLinkUrl", default="") or "",
        "employees": rec.get("employees"),
        "city": _g(rec, "address", "addressCity", default="") or "",
        "country": _g(rec, "address", "addressCountry", default="") or "",
        "linkedin": _g(rec, "linkedinLink", "primaryLinkUrl", default="") or "",
        # relation counts only present at depth>=1; degrade to None otherwise
        "peopleCount": _rel_count(people),
        "opportunitiesCount": _rel_count(opps),
        "createdAt": rec.get("createdAt"),
        "updatedAt": rec.get("updatedAt"),
    }


def opportunity_out(rec: dict) -> dict:
    """Twenty opportunity record -> flat opportunity (deal)."""
    company = rec.get("company") if isinstance(rec.get("company"), dict) else {}
    poc = rec.get("pointOfContact") if isinstance(rec.get("pointOfContact"), dict) else {}
    return {
        "id": rec.get("id"),
        "name": rec.get("name") or "Untitled deal",
        "stage": rec.get("stage") or "NEW",
        "amount": _money_major(rec),
        "currencyCode": _g(rec, "amount", "currencyCode", default="USD") or "USD",
        "closeDate": rec.get("closeDate"),
        "companyId": rec.get("companyId") or (company.get("id") if company else None),
        "companyName": company.get("name") if company else None,
        "pointOfContactId": rec.get("pointOfContactId") or (poc.get("id") if poc else None),
        "pointOfContactName": (_full_name(poc) if poc else None),
        "position": rec.get("position"),
        "createdAt": rec.get("createdAt"),
        "updatedAt": rec.get("updatedAt"),
    }


def note_out(rec: dict) -> dict:
    return {
        "id": rec.get("id"),
        "title": rec.get("title") or "",
        "body": _rich_text(rec),
        "createdAt": rec.get("createdAt"),
    }


def task_out(rec: dict) -> dict:
    return {
        "id": rec.get("id"),
        "title": rec.get("title") or "",
        "body": _rich_text(rec),
        "status": rec.get("status") or "TODO",
        "dueAt": rec.get("dueAt"),
        "createdAt": rec.get("createdAt"),
    }


def _rich_text(rec: dict) -> str:
    # bodyV2 (current) is {markdown, blocknote}; body (older) is a plain string.
    b2 = rec.get("bodyV2")
    if isinstance(b2, dict):
        return b2.get("markdown") or ""
    if isinstance(b2, str):
        return b2
    b = rec.get("body")
    return b if isinstance(b, str) else ""


def _rel_count(rel: Any) -> int | None:
    if isinstance(rel, list):
        return len(rel)
    if isinstance(rel, dict):
        if isinstance(rel.get("edges"), list):
            return len(rel["edges"])
        if rel.get("totalCount") is not None:
            return rel["totalCount"]
    return None


# ── writers (flat input -> Twenty create/update body) ────────────────────────
def person_in(flat: dict) -> dict:
    """Flat person -> Twenty create/update body. Only sends keys that are present
    so a PATCH never clobbers untouched fields."""
    out: dict[str, Any] = {}
    first = (flat.get("firstName") or "").strip()
    last = (flat.get("lastName") or "").strip()
    if not first and not last and flat.get("name"):
        first, last = _split_name(flat["name"])
    if first or last or "name" in flat:
        out["name"] = {"firstName": first, "lastName": last}
    if "email" in flat:
        out["emails"] = {"primaryEmail": (flat.get("email") or "").strip()}
    if "phone" in flat:
        out["phones"] = {"primaryPhoneNumber": (flat.get("phone") or "").strip()}
    for k in ("jobTitle", "city"):
        if k in flat and flat[k] is not None:
            out[k] = str(flat[k]).strip()
    if flat.get("companyId"):
        out["companyId"] = flat["companyId"]
    return out


def company_in(flat: dict) -> dict:
    out: dict[str, Any] = {}
    if "name" in flat:
        out["name"] = (flat.get("name") or "").strip()
    if "domain" in flat and flat.get("domain"):
        dom = str(flat["domain"]).strip()
        out["domainName"] = {"primaryLinkUrl": dom}
    # linkedin is a Links composite too — write it back so the field the client type
    # advertises as writable doesn't silently no-op (company_out reads it from here).
    if "linkedin" in flat and flat.get("linkedin"):
        out["linkedinLink"] = {"primaryLinkUrl": str(flat["linkedin"]).strip()}
    if flat.get("employees") is not None:
        try:
            out["employees"] = int(flat["employees"])
        except Exception:  # noqa: BLE001
            pass
    if flat.get("city") or flat.get("country"):
        out["address"] = {
            "addressCity": (flat.get("city") or "").strip(),
            "addressCountry": (flat.get("country") or "").strip(),
        }
    return out


def opportunity_in(flat: dict) -> dict:
    out: dict[str, Any] = {}
    if "name" in flat:
        out["name"] = (flat.get("name") or "").strip()
    if "stage" in flat and flat.get("stage"):
        out["stage"] = str(flat["stage"]).strip()
    if "amount" in flat and flat.get("amount") is not None:
        try:
            out["amount"] = {
                "amountMicros": int(round(float(flat["amount"]) * _MICROS)),
                "currencyCode": (flat.get("currencyCode") or "USD").strip() or "USD",
            }
        except Exception:  # noqa: BLE001
            pass
    if flat.get("closeDate"):
        out["closeDate"] = flat["closeDate"]
    if flat.get("companyId"):
        out["companyId"] = flat["companyId"]
    if flat.get("pointOfContactId"):
        out["pointOfContactId"] = flat["pointOfContactId"]
    return out


def _split_name(full: str) -> tuple[str, str]:
    parts = (full or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])
