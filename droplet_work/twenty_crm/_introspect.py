"""Introspect the live Twenty /metadata schema for the auth + api-key + workspace
mutations, so we build the provisioner against the EXACT deployed signatures."""
import json
import os

import httpx

META = os.environ.get("TWENTY_INTERNAL_URL", "http://twenty:3000") + "/metadata"


def gql(q, v=None):
    r = httpx.post(META, json={"query": q, "variables": v or {}},
                   headers={"Content-Type": "application/json"}, timeout=40)
    return r.json()


def tname(t):
    if not t:
        return None
    return t.get("name") or tname(t.get("ofType"))


d = gql("""
query { __schema { mutationType { fields {
  name args { name type { kind name ofType { kind name ofType { kind name ofType { kind name } } } } }
} } } }
""")
fields = (((d.get("data") or {}).get("__schema") or {}).get("mutationType") or {}).get("fields") or []
print("total mutations:", len(fields))
KW = ("signup", "signin", "login", "authtoken", "apikey", "workspace", "activate", "token")
for f in sorted(fields, key=lambda x: x["name"]):
    n = f["name"]
    if any(k in n.lower() for k in KW):
        args = [(a["name"], tname(a["type"])) for a in f["args"]]
        print(f"  {n}({', '.join(f'{a}:{t}' for a,t in args)})")

print("\n--- input/object types ---")
for tn in ["SignUpInNewWorkspaceInput", "CreateApiKeyInput", "ApiKeyTokenInput",
           "ActivateWorkspaceInput", "AvailableWorkspacesAndAccessTokensDTO",
           "SignUpDTO", "AuthTokens", "AuthToken", "ApiKey", "ApiKeyToken"]:
    dq = gql("query($n:String!){ __type(name:$n){ name kind "
             "inputFields { name type { kind name ofType { kind name } } } "
             "fields { name type { kind name ofType { kind name } } } } }", {"n": tn})
    t = (dq.get("data") or {}).get("__type")
    if t:
        flds = t.get("inputFields") or t.get("fields") or []
        names = [f"{f['name']}:{tname(f['type'])}" for f in flds]
        print(f"  {tn} [{t.get('kind')}]: {names}")
    else:
        print(f"  {tn}: (not found)")
