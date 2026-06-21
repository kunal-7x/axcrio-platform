# BIGGER-BOX-MIGRATION — STATE (durable; crash-safe)

Goal: a BIGGER, hardened, Cloudflare-fronted panel box in blr1 so panel.famit.in
stops OOM-crashing. PANEL/WEBSITE ONLY. **NEVER touch the voice earner box.**

## VOICE EARNER — DO NOT TOUCH (hard line)
- Voice/earner box = `famit-livekit` id=574914961, pub `168.144.153.145`, priv `10.122.0.4`.
  (Prompt quoted 168.144.153.145 as the earner; an old note said .145 — same box `famit-livekit`.)
  This box is the LIVE EARNER. No resize, no reboot, no firewall change, no SSH. Untouched.

## GROUND TRUTH (recon 2026-06-20)
- DO account `kunalkumar7x@gmail.com`, status=**warning**, **droplet_limit=3, 3 USED**.
  status_message: "created the maximum allowed number of Droplets. Please resolve this on the control panel."
- **POST /droplets -> HTTP 422 (BLOCKED).** Cannot create a 4th droplet via API. Raising the
  limit is a DO control-panel / support action = FOUNDER-ONLY (no API endpoint for it).
- 3 droplets: famit-livekit(8gb, EARNER), famit-panel-2(4gb, the panel), famit-hatchet(4gb).
- VPC (all 3) = `61f1950d-a7c4-4144-99b9-f1cda3d4c627` (default-blr1, 10.122.0.0/20).
- SSH key id 56622232 (c13-blr-test-key) == local `C:\Users\kunal\.ssh\do-blr-test\id_ed25519`
  (fp 17:a1:35:..:e3 MATCHES). Works for root + deployuser on the fortress boxes.
- Local pre-built artifact present: `caps\famit-panel\.next` (BUILD_ID osCm5x7UxrATqG-CUU99m), name=core-2.
- fortress-panel-fw (id c0e34e18) ALREADY EXISTS, tag=fortress, CF-IP-locked 80/443, SSH22, egress allow-list (53/123/80/443 + 8209/8310 to backend). Applied to panel box by tag.

## DECISION (founder-mindset, earner-safe)
NEW box is BLOCKED by the 3-droplet limit (422). The panel box `famit-panel-2` is ALREADY
fortress-hardened (18/18) + Cloudflare-fronted + serving panel.famit.in. The founder's true intent
(bigger box, no OOM, born-hardened, CF-fronted, panel-only) is delivered SAFEST by **resizing the
existing panel box 4GB -> 8GB in place** (disk-resize, reboot ~1-2 min). Zero new attack surface,
no migration risk, voice box untouched, respects the limit. Snapshot first = instant rollback.
=> PATH A = RESIZE IN PLACE. PATH B (truly separate new 8GB box) needs the founder to raise the
droplet limit in the DO dashboard first (the one click), then I provision+migrate per the fortress recipe.

## UNITS
- [x] U0 Recon (account/droplets/keys/fw/artifact) DONE
- [ ] U1 SSH panel box: confirm healthy + capture current RAM/disk/load (justify resize)
- [ ] U2 Snapshot panel box (rollback point) via DO API
- [ ] U3 Resize 4gb -> 8gb (s-4vcpu-8gb) [needs power-off; disk-resize]
- [ ] U4 Power on; verify 8GB RAM live; services up; sshd passwordauth=no; ports closed
- [ ] U5 Verify https://panel.famit.in = 200 THROUGH Cloudflare; origin not directly reachable on 443
- [ ] U6 Redeploy latest pre-built .next if newer than box (no build on box)
- [ ] U7 Record results + EARNER-LIVE-STATE note + founder one-click (raise limit if he wants separate box)

## ROLLBACK
- Resize down 8gb->4gb is also a DO API resize. Snapshot from U2 = full restore in ~2 min.
