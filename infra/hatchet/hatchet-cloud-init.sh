#!/bin/bash
# cloud-init user_data for famit-hatchet (F3). Born-hardened: installs Docker + OS hardening.
# Idempotent / re-runnable. Marker: /var/lib/hatchet-provisioned
set -euxo pipefail
exec > /var/log/hatchet-cloud-init.log 2>&1

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl gnupg ufw fail2ban unattended-upgrades jq

# --- Docker (official repo) ---
install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.asc ]; then
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
fi
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

# --- SSH hardening: key-only ---
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart ssh || systemctl restart sshd || true

# --- UFW: inbound 22 only (internals are localhost-bound + DO firewall is the real egress gate) ---
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw --force enable

# --- fail2ban (SSH) ---
systemctl enable --now fail2ban

# --- unattended security upgrades ---
echo 'APT::Periodic::Update-Package-Lists "1";' > /etc/apt/apt.conf.d/20auto-upgrades
echo 'APT::Periodic::Unattended-Upgrade "1";' >> /etc/apt/apt.conf.d/20auto-upgrades

# --- sysctl hardening ---
cat > /etc/sysctl.d/99-hatchet-harden.conf <<'EOF'
net.ipv4.tcp_syncookies=1
net.ipv4.conf.all.rp_filter=1
net.ipv4.conf.all.accept_source_route=0
net.ipv4.conf.all.accept_redirects=0
net.ipv4.conf.all.send_redirects=0
kernel.randomize_va_space=2
EOF
sysctl --system || true

# --- swap (build headroom for docker pulls on 4GB box) ---
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

mkdir -p /opt/hatchet
touch /var/lib/hatchet-provisioned
echo "hatchet cloud-init done $(date -u)" >> /var/lib/hatchet-provisioned
