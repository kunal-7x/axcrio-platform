#!/bin/bash
# Confirm the service is SETTLED: same MainPID, active, for ~12s
A_ACTIVE=$(systemctl is-active famit-agent)
A_PID=$(systemctl show famit-agent -p MainPID --value)
sleep 12
B_ACTIVE=$(systemctl is-active famit-agent)
B_PID=$(systemctl show famit-agent -p MainPID --value)
echo "active_before=$A_ACTIVE pid_before=$A_PID"
echo "active_after=$B_ACTIVE pid_after=$B_PID"
if [ "$A_ACTIVE" = "active" ] && [ "$B_ACTIVE" = "active" ] && [ "$A_PID" = "$B_PID" ] && [ -n "$A_PID" ] && [ "$A_PID" != "0" ]; then
  echo "SETTLED=YES"
else
  echo "SETTLED=NO"
fi
