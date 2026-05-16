#!/bin/bash
set -u
cd "$(dirname "$(readlink -f "$0")")"

export GEMINI_API_KEY=$(grep -E "^GEMINI_API_KEY=" .env | head -1 | cut -d= -f2-)

LOG=pipeline/results/_fc2_parallel.log
mkdir -p "$(dirname "$LOG")"
: > "$LOG"

WORKERS=4
MAX_RETRIES=3

mapfile -t SCENARIOS < <(find pipeline/configs/scenarios -path "*/1i_1a/fc2_infoflow_tp-strong/*.yaml" | sort)

CONDS=(basic trusting skeptical rational rational_trusting rational_skeptical)
declare -A SUFFIX=(
  [basic]=""
  [trusting]="_trusting"
  [skeptical]="_skeptical"
  [rational]="_rational"
  [rational_trusting]="_rational_trusting"
  [rational_skeptical]="_rational_skeptical"
)

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG" ; }

count_json() {
  local dir="$1"
  if [ -d "$dir" ]; then
    ls "$dir"/*.json 2>/dev/null | wc -l
  else
    echo 0
  fi
}

run_cell() {
  local yaml="$1"
  local cond="$2"
  local config_path="pipeline/configs/benchmark_${cond}.yaml"
  local slug=$(basename "$yaml" .yaml)
  local result_dir="pipeline/results/${slug}_fc2${SUFFIX[$cond]}"
  local have=$(count_json "$result_dir")

  if [ "$have" -ge 3 ]; then
    log "SKIP $cond/$slug (have $have)"
    return
  fi

  for attempt in $(seq 1 $MAX_RETRIES); do
    log "START $cond/$slug attempt=$attempt (have=$have)"
    uv run python pipeline/benchmark.py --file "$yaml" --config "$config_path" >> "$LOG" 2>&1
    have=$(count_json "$result_dir")
    if [ "$have" -ge 3 ]; then
      log "OK $cond/$slug (have=$have)"
      return
    fi
    log "RETRY $cond/$slug attempt=$attempt (have=$have)"
  done
  log "FAILED $cond/$slug after $MAX_RETRIES attempts (have=$have)"
}

TOTAL_CELLS=$(( ${#CONDS[@]} * ${#SCENARIOS[@]} ))
log "FC2 parallel benchmark: ${#SCENARIOS[@]} scenarios × ${#CONDS[@]} conditions = $TOTAL_CELLS cells, $WORKERS workers, $MAX_RETRIES retries"

for cond in "${CONDS[@]}"; do
  for yaml in "${SCENARIOS[@]}"; do
    run_cell "$yaml" "$cond" &

    while [ $(jobs -rp | wc -l) -ge $WORKERS ]; do
      wait -n
    done
  done
done

wait
log "All cells processed."
