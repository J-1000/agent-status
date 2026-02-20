#!/usr/bin/env bash
set -euo pipefail

printf "agent-status PRD assumption check (%s)\n" "$(date '+%Y-%m-%d %H:%M:%S %z')"

for cmd in ps lsof awk; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "missing required command: $cmd" >&2
    exit 1
  fi
done

echo
echo "== candidate sessions (pid ppid comm) =="
rows=()
while IFS= read -r line; do
  rows+=("$line")
done < <(ps -ax -o pid=,ppid=,comm= | awk '$3=="claude" || $3=="codex" {print $1" "$2" "$3}')
if [ ${#rows[@]} -eq 0 ]; then
  echo "none"
  exit 0
fi
printf '%s\n' "${rows[@]}"

echo
echo "== per-session details =="
for row in "${rows[@]}"; do
  pid="${row%% *}"
  ppid_comm="${row#* }"

  cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | awk '/^n/ {print substr($0,2); exit}')"
  env_line="$(ps -p "$pid" -wwwE 2>/dev/null || true)"
  surface_id="$(printf '%s\n' "$env_line" | tr ' ' '\n' | awk -F= '/^GHOSTTY_SURFACE_ID=/ {print $2; exit}')"
  if [ -z "${surface_id:-}" ]; then
    env_line2="$(ps -p "$pid" -eww -o command= 2>/dev/null || true)"
    surface_id="$(printf '%s\n' "$env_line2" | tr ' ' '\n' | awk -F= '/^GHOSTTY_SURFACE_ID=/ {print $2; exit}')"
  fi
  cpu_state="$(ps -p "$pid" -o pcpu=,state=,etime=,tty= 2>/dev/null | sed 's/^ *//')"

  printf 'pid=%s %s\n' "$pid" "$ppid_comm"
  printf '  cwd=%s\n' "${cwd:-unknown}"
  printf '  ghostty_surface_id=%s\n' "${surface_id:-missing}"
  printf '  cpu_state_etime_tty=%s\n' "${cpu_state:-missing}"
done

echo
echo "Interpretation checklist:"
echo "1) GHOSTTY_SURFACE_ID should look opaque (typically UUID-like) and differ across tabs/surfaces."
echo "2) If -wwwE misses GHOSTTY_SURFACE_ID, -eww fallback should still surface it."
echo "3) Parent/child pid chains indicate where nested session de-duplication applies."
echo "4) Compare %CPU while waiting vs actively generating to calibrate threshold."
