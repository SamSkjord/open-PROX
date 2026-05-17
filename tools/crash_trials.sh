#!/bin/bash
# Multi-trial crash timing harness for Hailo-10H stability testing.
# Each trial: power cycle Pi, wait for Hailo, run async_stress, record crash time.

TRIALS=${1:-5}
RESULTS_FILE="${2:-crash_trials.log}"
PI=pi@192.168.199.216
PLUG=192.168.199.69

echo "trial,cma_kb,fps,crash_frame,crash_elapsed_s,error" > "$RESULTS_FILE"

for i in $(seq 1 "$TRIALS"); do
  echo "=== Trial $i/$TRIALS ==="

  echo "  powering off..."
  kasa --host "$PLUG" --type plug off >/dev/null 2>&1
  sleep 20
  echo "  powering on..."
  kasa --host "$PLUG" --type plug on >/dev/null 2>&1

  echo "  waiting for Hailo..."
  for attempt in 1 2 3; do
    tries=0
    while ! ssh -o ConnectTimeout=3 "$PI" "ls /dev/hailo0 >/dev/null 2>&1"; do
      sleep 10
      tries=$((tries + 1))
      if [ $tries -gt 15 ]; then break; fi
    done
    if ssh "$PI" "ls /dev/hailo0 >/dev/null 2>&1"; then
      break
    fi
    echo "  boot lottery hit, retrying (attempt $attempt)..."
    kasa --host "$PLUG" --type plug off >/dev/null 2>&1
    sleep 30
    kasa --host "$PLUG" --type plug on >/dev/null 2>&1
  done

  if ! ssh "$PI" "ls /dev/hailo0 >/dev/null 2>&1"; then
    echo "  FAILED to boot Hailo after 3 attempts, skipping trial"
    echo "$i,0,0,0,-1,boot_failure" >> "$RESULTS_FILE"
    continue
  fi

  CMA=$(ssh "$PI" "grep CmaTotal /proc/meminfo | awk '{print \$2}'")
  echo "  Hailo ready, CMA=${CMA}kB, running stress..."

  OUTPUT=$(ssh "$PI" "timeout 300 ~/prox-env-312/bin/python3 ~/async_stress.py 2>&1")

  CRASH_LINE=$(echo "$OUTPUT" | grep "^CRASH " | head -1)
  LAST_FRAME=$(echo "$OUTPUT" | grep "^frame=" | tail -1)

  if [ -n "$CRASH_LINE" ]; then
    FRAME=$(echo "$CRASH_LINE" | sed -n 's/.*frame=\([0-9]*\).*/\1/p')
    ELAPSED=$(echo "$CRASH_LINE" | sed -n 's/.*elapsed=\([0-9.]*\)s.*/\1/p')
    FPS=$(echo "$LAST_FRAME" | sed -n 's/.*fps=\([0-9.]*\).*/\1/p')
    ERR=$(echo "$CRASH_LINE" | sed -n 's/.*: \(.*\)/\1/p' | head -c 80)
    echo "  CRASH frame=$FRAME elapsed=${ELAPSED}s fps=$FPS"
    echo "$i,$CMA,$FPS,$FRAME,$ELAPSED,\"$ERR\"" >> "$RESULTS_FILE"
  else
    echo "  no crash within timeout (300s)"
    FRAME=$(echo "$LAST_FRAME" | sed -n 's/frame=\([0-9]*\).*/\1/p')
    FPS=$(echo "$LAST_FRAME" | sed -n 's/.*fps=\([0-9.]*\).*/\1/p')
    echo "$i,$CMA,$FPS,$FRAME,999,no_crash_within_300s" >> "$RESULTS_FILE"
  fi
done

echo "=== Done. Results in $RESULTS_FILE ==="
cat "$RESULTS_FILE"
