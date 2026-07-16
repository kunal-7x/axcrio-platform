"""
twenty_crm.provision — headless, zero-touch per-tenant Twenty workspace provisioning.

When Twenty is self-hosted INSIDE Haptica (TWENTY_SELF_HOST=1), each Haptica tenant
gets its OWN isolated Twenty workspace the first time they open Sales CRM — no API
key, no clicks. This module runs the auth→workspace→API-key chain entirely
server-to-server and hands back a durable API-key token Haptica stores per tenant.

Chain VERIFIED against self-hosted Twenty **v2.14.4** (the schema differs between
versions — this is pinned + probed, see deploy/docker-compose.twenty.yml TWENTY_TAG):
  1. signUp(email,password)                  -> workspace-agnostic access token
  2. signUpInNewWorkspace                     -> loginToken + workspace.id + subdomainUrl
  3. getAuthTokensFromLoginToken(lt, origin)  -> workspace access token
  4. activateWorkspace(data:{displayName})    -> activates (seeds roles + data model)
  5. getRoles                                 -> the workspace Admin role id
  6. createApiKey(input:{name,expiresAt,roleId}) -> apiKey id
  7. generateApiKeyToken(apiKeyId,expiresAt)  -> the long-lived Bearer token

Identity is DETERMINISTIC per tenant (email+password derived from a server secret +
tenant_id), so a retry after a partial failure re-authenticates the same user
instead of orphaning accounts. The password is never needed after provisioning (the
API key is the durable credential) and never leaves the server.

Hard limit: a self-hosted Twenty server allows **5 workspaces** without an
enterprise key — step 2 raises a capacity ProvisionError beyond that.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac

import httpx

# An effectively-non-expiring API key (Twenty signs the JWT to this date).
FAR_EXPIRY = "2125-01-01T00:00:00.000Z"


class ProvisionError(Exception):
    """A provisioning failure. ``capacity=True`` means the server hit its
    workspace cap (needs an enterprise key / a second Twenty server)."""

    def __init__(self, message: str, *, capacity: bool = False):
        super().__init__(message)
        self.message = message
        self.capacity = capacity


# ── deterministic per-tenant identity ────────────────────────────────────────
def tenant_email(tenant_id: str, domain: str) -> str:
    slug = hashlib.sha256(tenant_id.encode()).hexdigest()[:16]
    return f"t-{slug}@{domain}"


def tenant_password(tenant_id: str, secret: str) -> str:
    # Stable, complex (>=upper/lower/digit), derived — so re-provision can sign back in.
    h = hmac.new((secret or "haptica").encode(), tenant_id.encode(), hashlib.sha256).hexdigest()
    return f"Hp{h[:28]}aA1"


# ── GraphQL plumbing ─────────────────────────────────────────────────────────
async def _gql(cli: httpx.AsyncClient, url: str, query: str,
               variables: dict | None = None, token: str | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = await cli.post(url, json={"query": query, "variables": variables or {}}, headers=headers)
    except httpx.HTTPError as e:
        raise ProvisionError(f"Twenty unreachable: {e!s}")
    try:
        data = r.json()
    except Exception:  # noqa: BLE001
        raise ProvisionError(f"Twenty returned non-JSON ({r.status_code})")
    if isinstance(data, dict) and data.get("errors"):
        raise _to_error(data["errors"])
    return (data or {}).get("data") or {}


def _to_error(errors) -> ProvisionError:
    msg = ""
    try:
        msg = errors[0].get("message") or ""
    except Exception:  # noqa: BLE001
        pass
    low = msg.lower()
    cap = ("workspace" in low and any(k in low for k in ("limit", "maximum", "reached", "cap")))
    return ProvisionError(msg or "Twenty GraphQL error", capacity=cap)


def _dig(d, *path):
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


_SIGNUP = """
mutation($email:String!,$password:String!){
  signUp(email:$email,password:$password){
    tokens { accessOrWorkspaceAgnosticToken { token } }
  }
}"""

_SIGNIN = """
mutation($email:String!,$password:String!){
  signIn(email:$email,password:$password){
    tokens { accessOrWorkspaceAgnosticToken { token } }
  }
}"""

_CREATE_WS = """
mutation{
  signUpInNewWorkspace{
    loginToken { token }
    workspace { id workspaceUrls { subdomainUrl } }
  }
}"""

_AUTH_FROM_LOGIN = """
mutation($loginToken:String!,$origin:String!){
  getAuthTokensFromLoginToken(loginToken:$loginToken,origin:$origin){
    tokens { accessOrWorkspaceAgnosticToken { token } }
  }
}"""

_ACTIVATE = """
mutation($displayName:String!){
  activateWorkspace(data:{displayName:$displayName}){ id }
}"""

_ROLES = "query{ getRoles{ id label canUpdateAllSettings } }"


def _create_key_mutation(role_id: str) -> str:
    # role_id is a server-issued UUID + the rest are constants -> safe to inline.
    return ('mutation{ createApiKey(input:{name:"Haptica", '
            f'expiresAt:"{FAR_EXPIRY}", roleId:"{role_id}"}}){{ id }} }}')


def _gen_token_mutation(api_key_id: str) -> str:
    return (f'mutation{{ generateApiKeyToken(apiKeyId:"{api_key_id}", '
            f'expiresAt:"{FAR_EXPIRY}"){{ token }} }}')


# ── the provisioner ──────────────────────────────────────────────────────────
async def provision_workspace(internal_url: str, *, tenant_id: str, secret: str,
                              domain: str, display_name: str = "Sales CRM",
                              roles_timeout_s: float = 25.0) -> dict:
    """Run the full chain for one tenant. Returns
    {api_key, workspace_id, email}. Raises ProvisionError on any failure."""
    meta = internal_url.rstrip("/") + "/metadata"
    email = tenant_email(tenant_id, domain)
    password = tenant_password(tenant_id, secret)

    async with httpx.AsyncClient(timeout=40) as cli:
        # 1. signUp (or signIn if the user already exists from a prior attempt)
        try:
            d = await _gql(cli, meta, _SIGNUP, {"email": email, "password": password})
            agnostic = _dig(d, "signUp", "tokens", "accessOrWorkspaceAgnosticToken", "token")
        except ProvisionError as e:
            low = e.message.lower()
            if any(k in low for k in ("already", "exist", "taken", "in use")):
                d = await _gql(cli, meta, _SIGNIN, {"email": email, "password": password})
                agnostic = _dig(d, "signIn", "tokens", "accessOrWorkspaceAgnosticToken", "token")
            else:
                raise
        if not agnostic:
            raise ProvisionError("Twenty signUp returned no token")

        # 2. create the tenant's isolated workspace
        d = await _gql(cli, meta, _CREATE_WS, token=agnostic)
        node = d.get("signUpInNewWorkspace") or {}
        login_token = _dig(node, "loginToken", "token")
        ws = node.get("workspace") or {}
        workspace_id = ws.get("id")
        subdomain_url = _dig(ws, "workspaceUrls", "subdomainUrl")
        if not login_token or not workspace_id:
            raise ProvisionError("Twenty workspace creation failed")

        # 3. exchange the login token for a workspace access token
        origin = subdomain_url or internal_url
        d = await _gql(cli, meta, _AUTH_FROM_LOGIN, {"loginToken": login_token, "origin": origin})
        access = _dig(d, "getAuthTokensFromLoginToken", "tokens",
                      "accessOrWorkspaceAgnosticToken", "token")
        if not access:
            raise ProvisionError("Twenty access-token exchange failed")

        # 4. activate (seeds roles + the data model)
        await _gql(cli, meta, _ACTIVATE, {"displayName": display_name or "Sales CRM"}, token=access)

        # 5. resolve the Admin role id (role seeding may lag activation slightly)
        role_id = None
        waited = 0.0
        while waited <= roles_timeout_s:
            d = await _gql(cli, meta, _ROLES, token=access)
            roles = d.get("getRoles") or []
            if roles:
                for r in roles:
                    if "admin" in (r.get("label") or "").lower() or r.get("canUpdateAllSettings"):
                        role_id = r.get("id")
                        break
                role_id = role_id or roles[0].get("id")
                if role_id:
                    break
            await asyncio.sleep(1.5)
            waited += 1.5
        if not role_id:
            raise ProvisionError("Twenty workspace roles were not ready in time")

        # 6. create the API key, then 7. mint its long-lived token
        d = await _gql(cli, meta, _create_key_mutation(role_id), token=access)
        api_key_id = _dig(d, "createApiKey", "id")
        if not api_key_id:
            raise ProvisionError("Twenty createApiKey failed")
        d = await _gql(cli, meta, _gen_token_mutation(api_key_id), token=access)
        api_key = _dig(d, "generateApiKeyToken", "token")
        if not api_key:
            raise ProvisionError("Twenty generateApiKeyToken failed")

        return {"api_key": api_key, "workspace_id": workspace_id, "email": email}


# ── optional: clear the demo records Twenty seeds on activation ───────────────
async def purge_seed_data(internal_url: str, api_key: str, *, cap: int = 80) -> int:
    """Best-effort delete of the example companies/people/opportunities Twenty seeds
    on a fresh workspace, so the client starts with an EMPTY CRM. Never raises."""
    rest = internal_url.rstrip("/") + "/rest"
    headers = {"Authorization": f"Bearer {api_key}"}
    deleted = 0
    async with httpx.AsyncClient(timeout=30) as cli:
        for obj in ("opportunities", "notes", "tasks", "people", "companies"):
            try:
                for _ in range(3):  # a few pages
                    r = await cli.get(f"{rest}/{obj}", params={"limit": 60, "depth": 0}, headers=headers)
                    if r.status_code != 200:
                        break
                    data = r.json()
                    recs = (((data or {}).get("data") or {}).get(obj)) or []
                    if not isinstance(recs, list) or not recs:
                        break
                    for rec in recs:
                        rid = rec.get("id")
                        if not rid or deleted >= cap:
                            continue
                        try:
                            await cli.delete(f"{rest}/{obj}/{rid}", headers=headers)
                            deleted += 1
                        except httpx.HTTPError:
                            pass
                    if deleted >= cap:
                        break
            except Exception:  # noqa: BLE001
                continue
    return deleted
