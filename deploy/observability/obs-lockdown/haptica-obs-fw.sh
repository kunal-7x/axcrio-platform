#!/bin/bash
# Restrict the observability droplet's Docker-PUBLISHED ports to haptica-prod ONLY.
# Docker-published ports bypass UFW (they're DNAT'd in the FORWARD/DOCKER chains before UFW's
# INPUT), so without this they're reachable from the public internet. The DOCKER-USER chain is
# the supported hook for filtering Docker traffic.
#
# SOURCE-BASED (interface-agnostic) so it's correct regardless of NIC names (eth0/ens*/eth1/VPC):
# for the telemetry/query ports we RETURN (allow) traffic from haptica-prod, from Docker's own
# bridge subnets (so SigNoz/Prometheus internals keep working), and from loopback — and DROP
# everyone else. Idempotent (removes its own rules before re-adding). Re-applied on boot AND on
# docker restart via haptica-obs-fw.service (PartOf=docker.service).
set -u
PROD="${HAPTICA_PROD_IP:-168.144.85.191}"
PORTS="8123,8080,9090,3000,4317,4318"   # clickhouse, signoz, prometheus, grafana, otlp grpc/http
DOCKER_NET="172.16.0.0/12"              # Docker default bridge/user-network range (inter-container)

del() { iptables -D DOCKER-USER "$@" 2>/dev/null || true; }
# remove prior copies (idempotent)
del -p tcp -m multiport --dports "$PORTS" -s "$PROD" -j RETURN
del -p tcp -m multiport --dports "$PORTS" -s 127.0.0.0/8 -j RETURN
del -p tcp -m multiport --dports "$PORTS" -s "$DOCKER_NET" -j RETURN
del -p tcp -m multiport --dports "$PORTS" -j DROP

# Insert in REVERSE of desired order (each -I prepends): final top-down =
#   RETURN prod, RETURN loopback, RETURN docker-net, DROP everyone-else-to-those-ports.
iptables -I DOCKER-USER -p tcp -m multiport --dports "$PORTS" -j DROP
iptables -I DOCKER-USER -p tcp -m multiport --dports "$PORTS" -s "$DOCKER_NET" -j RETURN
iptables -I DOCKER-USER -p tcp -m multiport --dports "$PORTS" -s 127.0.0.0/8 -j RETURN
iptables -I DOCKER-USER -p tcp -m multiport --dports "$PORTS" -s "$PROD" -j RETURN
