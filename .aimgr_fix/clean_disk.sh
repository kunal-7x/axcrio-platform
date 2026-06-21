#!/bin/bash
set -u
cd /opt/famit-panel || exit 1
# KEEP the current .next + the most-recent good backup (R6UIbak) as rollback. Remove the rest.
KEEP=".next.R6UIbak.20260620-005046"
echo "before:"; df -h /opt | tail -1
for d in .next.A1bak.* .next.UIbak.* .next.FIXUIbak.* .next.PVSUIbak.* \
         .next.PERFUIbak.* .next.RECUIbak.* .next.deploybak .next.PERFbak.* \
         .next.W1bak.* .next.PVbak.* .next.UNIFYbak.* .next.WFbak.* \
         .next.W4bak.* .next.leadsmgmtbak.* .next.R4SHIPbak.* .next.R5UIbak.* \
         .next.R5UI2bak.* .next.CORRUPT.* .next.prev-* .next.bak.* \
         .next.WAPbak.* .next.aimcallhist.*; do
  if [ -e "$d" ] && [ "$d" != "$KEEP" ]; then
    rm -rf "$d" && echo "deleted $d"
  fi
done
echo "after:"; df -h /opt | tail -1
echo "remaining .next dirs:"; ls -d .next* 2>/dev/null
