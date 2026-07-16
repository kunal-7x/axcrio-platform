"""Systematic probe of the v2.14.4 headless provisioning chain (introspection is
off, so we trial variants and report the winning query for each step)."""
import json
import os
import secrets

import httpx

BASE = os.environ.get("TWENTY_INTERNAL_URL", "http://twenty:3000")
META = BASE + "/metadata"
REST = BASE + "/rest"
FAR = "2125-01-01T00:00:00.000Z"


def gql(q, t=None):
    h = {"Content-Type": "application/json"}
    if t:
        h["Authorization"] = f"Bearer {t}"
    try:
        r = httpx.post(META, json={"query": q}, headers=h, timeout=40)
    except Exception as e:  # noqa: BLE001
        return 0, {"_exc": str(e)}
    try:
        return r.status_code, r.json()
    except Exception:  # noqa: BLE001
        return r.status_code, {"_raw": r.text[:600]}


def ok(d):
    return isinstance(d, dict) and d.get("data") and not d.get("errors")


def errs(d):
    return json.dumps(d.get("errors"))[:500] if isinstance(d, dict) and d.get("errors") else ""


email = f"probe-{secrets.token_hex(4)}@haptica.local"
pw = "Pb" + secrets.token_hex(10) + "aA1"

sc, d = gql(f'mutation{{ signUp(email:"{email}",password:"{pw}"){{ tokens{{ accessOrWorkspaceAgnosticToken{{ token }} }} }} }}')
ag = (((d.get("data") or {}).get("signUp") or {}).get("tokens") or {}).get("accessOrWorkspaceAgnosticToken", {}).get("token")
print("1 signUp:", "OK" if ag else "FAIL", errs(d))
assert ag, "signUp failed"

login = wsid = suburl = win = None
for sel in [
    "loginToken{ token } workspace{ id workspaceUrls{ subdomainUrl } }",
    "loginToken workspace{ id workspaceUrls{ subdomainUrl } }",
    "loginToken{ token } workspace{ id }",
]:
    sc, d = gql(f'mutation{{ signUpInNewWorkspace{{ {sel} }} }}', t=ag)
    if ok(d):
        node = d["data"]["signUpInNewWorkspace"]
        win = sel
        lt = node.get("loginToken")
        login = lt.get("token") if isinstance(lt, dict) else lt
        ws = node.get("workspace") or {}
        wsid = ws.get("id")
        suburl = (ws.get("workspaceUrls") or {}).get("subdomainUrl")
        break
    else:
        print("  2 try err:", errs(d))
print("2 signUpInNewWorkspace:", "OK" if login else "FAIL", "| sel=", win, "| wsid=", wsid, "| suburl=", suburl)
assert login, "create workspace failed"

access = None
for origin in [suburl, BASE]:
    if not origin:
        continue
    sc, d = gql(f'mutation{{ getAuthTokensFromLoginToken(loginToken:"{login}",origin:"{origin}"){{ tokens{{ accessOrWorkspaceAgnosticToken{{ token }} }} }} }}')
    if ok(d):
        access = d["data"]["getAuthTokensFromLoginToken"]["tokens"]["accessOrWorkspaceAgnosticToken"]["token"]
        print("3 getAuthTokens: OK | origin=", origin)
        break
    else:
        print("  3 origin", origin, "err:", errs(d))
assert access, "access token failed"

# 3.5 activate the workspace (seeds standard roles + the data model)
import time
activated = False
for data in ['{displayName:"Haptica CRM"}', '{displayName:"Haptica"}', '{}']:
    sc, d = gql(f'mutation{{ activateWorkspace(data:{data}){{ id }} }}', t=access)
    if ok(d):
        activated = True
        print("3.5 activateWorkspace: OK | data", data)
        break
    else:
        print("  3.5 activate err:", data, errs(d))
print("3.5 activated:", activated)

# 4 roles (retry — role seeding may run via the worker just after activation)
roleid = None
for attempt in range(10):
    sc, d = gql("query{ getRoles{ id label canUpdateAllSettings } }", t=access)
    if ok(d):
        arr = d["data"].get("getRoles") or []
        if arr:
            for r in arr:
                if "admin" in (r.get("label") or "").lower() or r.get("canUpdateAllSettings"):
                    roleid = r.get("id")
                    break
            roleid = roleid or arr[0].get("id")
            print(f"4 roles: OK -> roleid {roleid} of {len(arr)} (attempt {attempt+1})")
            break
    time.sleep(1.5)
if not roleid:
    print("4 roles: still empty after retries", errs(d))

keyid = None
for inp in [f'{{name:"Haptica", expiresAt:"{FAR}", roleId:"{roleid}"}}',
            f'{{name:"Haptica", expiresAt:"{FAR}"}}']:
    if "roleId" in inp and not roleid:
        continue
    sc, d = gql(f'mutation{{ createApiKey(input:{inp}){{ id name expiresAt }} }}', t=access)
    if ok(d):
        keyid = d["data"]["createApiKey"]["id"]
        print("5 createApiKey: OK ->", keyid, "| input", inp[:70])
        break
    else:
        print("  5 createApiKey err:", errs(d))
assert keyid, "createApiKey failed"

tok = None
sc, d = gql(f'mutation{{ generateApiKeyToken(apiKeyId:"{keyid}",expiresAt:"{FAR}"){{ token }} }}', t=access)
if ok(d):
    tok = d["data"]["generateApiKeyToken"]["token"]
    print("6 generateApiKeyToken: OK")
else:
    print("6 generateApiKeyToken: FAIL", errs(d))
assert tok, "generateApiKeyToken failed"

r = httpx.get(REST + "/companies", params={"limit": 1, "depth": 0},
              headers={"Authorization": f"Bearer {tok}"}, timeout=30)
print("7 REST /companies ->", r.status_code, r.text[:200])
print("RESULT:", "CHAIN_OK" if r.status_code == 200 else "CHAIN_FAIL")
print("CLEANUP_WS:", wsid)
