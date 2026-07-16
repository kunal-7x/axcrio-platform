#!/usr/bin/env python3
"""
Provision the Haptica AI production droplet on DigitalOcean.

Run this YOURSELF (it acts with your authorization, which the agent's safety
gate requires for changes to the shared DO account):

    ! python3 "<repo>/infra/provision-droplet.py"

It is idempotent: re-running won't create a second droplet — it reuses the
existing 'haptica-prod' and just re-prints its IP.

What it does:
  1. Reads DO_API_TOKEN (from env, else axcrio-platform/.env.local).
  2. Registers your SSH public key with the account (if not already there).
  3. Creates a 16 GB / 8 vCPU droplet in BLR1 (Ubuntu 24.04) with a cloud-init
     that immediately closes the attack window: UFW default-deny + SSH only,
     fail2ban, unattended security updates, and a 4 GB swap safety net.
  4. Waits for it to boot and prints DROPLET_IP for the agent to take over.
"""
import json, os, sys, time, urllib.request, urllib.error

ENV_FALLBACK = os.path.expanduser(
    "~/Documents/Aqulia Industries/Prateek-Mathur-Client/axcrio-platform/.env.local"
)
PUBKEY_PATH = os.path.expanduser("~/.ssh/id_ed25519.pub")
# NOTE: 16GB (s-8vcpu-16gb) is restricted on this account tier until it's verified
# / a tier-increase ticket is granted. Starting on 8GB (the largest currently
# allowed, == famit-livekit); RESIZE to s-8vcpu-16gb before go-live once unlocked.
NAME, REGION, SIZE, IMAGE = "haptica-prod", "blr1", "s-4vcpu-8gb", "ubuntu-24-04-x64"

CLOUD_INIT = """#cloud-config
package_update: true
package_upgrade: false
packages: [ufw, fail2ban, unattended-upgrades]
runcmd:
  - ufw default deny incoming
  - ufw default allow outgoing
  - ufw allow OpenSSH
  - ufw --force enable
  - systemctl enable --now fail2ban
  - bash -c 'if ! swapon --show | grep -q swapfile; then fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo "/swapfile none swap sw 0 0" >> /etc/fstab; fi'
  - dpkg-reconfigure -f noninteractive unattended-upgrades
"""


def read_token() -> str:
    tok = os.environ.get("DO_API_TOKEN")
    if tok:
        return tok.strip()
    try:
        with open(ENV_FALLBACK) as f:
            for line in f:
                if line.startswith("DO_API_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    sys.exit("DO_API_TOKEN not found (set env or check axcrio-platform/.env.local)")


TOK = read_token()


def api(method, path, body=None):
    req = urllib.request.Request(
        "https://api.digitalocean.com/v2" + path, method=method,
        headers={"Authorization": "Bearer " + TOK, "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return json.load(e)
        except Exception:
            return {"message": f"HTTP {e.code}"}


def main():
    pub = open(PUBKEY_PATH).read().strip()
    pub_body = pub.split()[1]

    # 1. SSH key (idempotent)
    keys = api("GET", "/account/keys").get("ssh_keys", [])
    fp = next((k["fingerprint"] for k in keys
               if k.get("public_key", "").split()[1:2] == [pub_body]), None)
    if not fp:
        r = api("POST", "/account/keys",
                {"name": "haptica-deploy-nikhil", "public_key": pub})
        fp = (r.get("ssh_key") or {}).get("fingerprint")
        if not fp:
            sys.exit(f"could not register SSH key: {r.get('message', r)}")
    print("ssh-key-fingerprint:", fp)

    # 2. droplet (idempotent on name)
    drops = api("GET", "/droplets?per_page=100").get("droplets", [])
    d = next((x for x in drops if x["name"] == NAME), None)
    if d:
        print("reusing existing droplet id:", d["id"])
    else:
        r = api("POST", "/droplets", {
            "name": NAME, "region": REGION, "size": SIZE, "image": IMAGE,
            "ssh_keys": [fp], "backups": False, "monitoring": True,
            "ipv6": True, "user_data": CLOUD_INIT, "tags": ["haptica"],
        })
        d = r.get("droplet")
        if not d:
            sys.exit(f"droplet create failed: {r.get('message', r)}")
        print("created droplet id:", d["id"])

    # 3. wait for active + public IP
    did = d["id"]
    ip = None
    for _ in range(72):  # ~6 min
        dd = api("GET", f"/droplets/{did}").get("droplet", {})
        if dd.get("status") == "active":
            ip = next((n["ip_address"] for n in dd.get("networks", {}).get("v4", [])
                       if n["type"] == "public"), None)
            if ip:
                break
        time.sleep(5)

    print("=" * 50)
    if ip:
        print("STATUS: active")
        print("DROPLET_IP:", ip)
        print("Hand this IP back to Claude to continue the secure deploy.")
    else:
        print("STATUS: still provisioning — re-run this script in a minute to get the IP.")
    print("=" * 50)


if __name__ == "__main__":
    main()
