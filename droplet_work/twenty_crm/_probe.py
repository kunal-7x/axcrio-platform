"""One-off probe: validate the headless signUp -> workspace -> API-key chain against
the LIVE self-hosted Twenty (run inside the docker network, talks to twenty:3000).
Prints each step so we can confirm exact mutation names/fields for THIS version
before baking the provisioner. Tolerant of failures — reports where it breaks."""
import json
import os
import secrets

import httpx

BASE = os.environ.get("TWENTY_INTERNAL_URL", "http://twenty:3000")
META = BASE + "/metadata"
REST = BASE + "/rest"
FAR = "2125-01-01T00:00:00.000Z"  # ~100y expiry


def gql(url, query, variables=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = httpx.post(url, json={"query": query, "variables": variables or {}},
                       headers=headers, timeout=40)
    except Exception as e:  # noqa: BLE001
        return 0, {"_exc": str(e)}
    try:
        return r.status_code, r.json()
    except Exception:  # noqa: BLE001
        return r.status_code, {"_raw": r.text[:800]}


def show(label, sc, d):
    print(f"\n=== {label} (http {sc}) ===")
    s = json.dumps(d)
    print(s[:1200])
    if isinstance(d, dict) and d.get("errors"):
        print("  ERRORS:", json.dumps(d["errors"])[:800])


email = f"probe-{secrets.token_hex(4)}@haptica.local"
pw = "Pb" + secrets.token_hex(10) + "!aA1"
print("probe email:", email)

# 1. signUp -> workspace-agnostic token
sc, d = gql(META, """
mutation S($email:String!,$password:String!){
  signUp(email:$email,password:$password){
    tokens { accessOrWorkspaceAgnosticToken { token expiresAt } refreshToken { token } }
  }
}""", {"email": email, "password": pw})
show("1 signUp", sc, d)
agnostic = (((d.get("data") or {}).get("signUp") or {}).get("tokens") or {}) \
    .get("accessOrWorkspaceAgnosticToken", {}).get("token") if isinstance(d, dict) else None
print("  -> agnostic token:", bool(agnostic))
if not agnostic:
    raise SystemExit("signUp failed — cannot continue")

# 2. signUpInNewWorkspace -> loginToken + workspace
sub = "t" + secrets.token_hex(5)
sc, d = gql(META, """
mutation SNW($input:SignUpInNewWorkspaceInput){
  signUpInNewWorkspace(input:$input){
    loginToken { token expiresAt }
    workspace { id workspaceUrls { subdomainUrl customUrl } }
  }
}""", {"input": {"displayName": "Probe Co", "subdomain": sub}}, token=agnostic)
show("2 signUpInNewWorkspace", sc, d)
snw = ((d.get("data") or {}).get("signUpInNewWorkspace") or {}) if isinstance(d, dict) else {}
login_token = (snw.get("loginToken") or {}).get("token")
ws = snw.get("workspace") or {}
ws_id = ws.get("id")
urls = ws.get("workspaceUrls") or {}
subdomain_url = urls.get("subdomainUrl")
print("  -> loginToken:", bool(login_token), "| ws_id:", ws_id, "| subdomainUrl:", subdomain_url)
if not login_token:
    raise SystemExit("signUpInNewWorkspace failed — cannot continue")

# 3. getAuthTokensFromLoginToken -> access token  (try subdomainUrl, then SERVER_URL)
access = None
for origin in [subdomain_url, BASE, os.environ.get("TWENTY_SERVER_URL", "http://twenty:3000")]:
    if not origin:
        continue
    sc, d = gql(META, """
    mutation GA($loginToken:String!,$origin:String!){
      getAuthTokensFromLoginToken(loginToken:$loginToken,origin:$origin){
        tokens { accessOrWorkspaceAgnosticToken { token expiresAt } }
      }
    }""", {"loginToken": login_token, "origin": origin}, token=None)
    show(f"3 getAuthTokensFromLoginToken origin={origin}", sc, d)
    access = (((d.get("data") or {}).get("getAuthTokensFromLoginToken") or {}).get("tokens") or {}) \
        .get("accessOrWorkspaceAgnosticToken", {}).get("token") if isinstance(d, dict) else None
    if access:
        print("  -> ACCESS token via origin:", origin)
        break
if not access:
    raise SystemExit("getAuthTokensFromLoginToken failed for all origins")

# 4. roles -> admin roleId  (try a couple of shapes)
role_id = None
for q in [
    "query{ roles { id label } }",
    "query{ getRoles { id label } }",
    "query{ roles { id name } }",
]:
    sc, d = gql(META, q, token=access)
    show("4 roles query", sc, d)
    roles = None
    if isinstance(d, dict) and d.get("data"):
        roles = d["data"].get("roles") or d["data"].get("getRoles")
    if roles:
        # prefer an 'admin' label
        for r in roles:
            lab = (r.get("label") or r.get("name") or "").lower()
            if "admin" in lab:
                role_id = r.get("id"); break
        role_id = role_id or roles[0].get("id")
        print("  -> roleId:", role_id, "from", len(roles), "roles")
        break

# 5. createApiKey -> id
api_key_id = None
if role_id:
    sc, d = gql(META, """
    mutation CK($input:CreateApiKeyInput!){ createApiKey(input:$input){ id name expiresAt } }
    """, {"input": {"name": "Haptica", "expiresAt": FAR, "roleId": role_id}}, token=access)
    show("5 createApiKey", sc, d)
    api_key_id = ((d.get("data") or {}).get("createApiKey") or {}).get("id") if isinstance(d, dict) else None
    print("  -> apiKeyId:", api_key_id)

# 6. generateApiKeyToken -> token
final_token = None
if api_key_id:
    sc, d = gql(META, """
    mutation GK($apiKeyId:UUID!,$expiresAt:String!){ generateApiKeyToken(apiKeyId:$apiKeyId,expiresAt:$expiresAt){ token } }
    """, {"apiKeyId": api_key_id, "expiresAt": FAR}, token=access)
    show("6 generateApiKeyToken", sc, d)
    final_token = ((d.get("data") or {}).get("generateApiKeyToken") or {}).get("token") if isinstance(d, dict) else None
    print("  -> API KEY TOKEN minted:", bool(final_token))

# 7. use the token against the data API
if final_token:
    try:
        r = httpx.get(REST + "/companies", params={"limit": 1, "depth": 0},
                      headers={"Authorization": f"Bearer {final_token}"}, timeout=30)
        print(f"\n=== 7 REST /companies with minted key -> http {r.status_code} ===")
        print(r.text[:400])
        print("\nRESULT: FULL CHAIN OK" if r.status_code == 200 else "\nRESULT: token minted but REST failed")
    except Exception as e:  # noqa: BLE001
        print("REST test exception:", e)
    print("WORKSPACE_ID_TO_CLEANUP:", ws_id)
