#!/usr/bin/env bash
# Measure Nexus Command Center resource use and write build/benchmarks/<host>-<date>.json.
#
#   scripts/benchmarks/command-center.sh [--installed] [--idle SECONDS] [--runs N]
#
# Measures (real numbers, never estimates):
#   * startup to first window (ms) and idle RSS/CPU on a plain launch (Overview only)
#   * per-module controller and page load times, RSS/CPU after visiting all 14 modules
#   * background processes left by the Command Center (expected: none)
#   * whether Docker / Ollama were running during the measurement
# Without --installed the repository sources are used. Use a real desktop session
# (Wayland) for representative numbers; QT_QPA_PLATFORM=offscreen is used if no display.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
IDLE=20
RUNS=3
INSTALLED=0
while [ $# -gt 0 ]; do
    case "$1" in
        --installed) INSTALLED=1; shift ;;
        --idle) IDLE="$2"; shift 2 ;;
        --runs) RUNS="$2"; shift 2 ;;
        -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
done

if [ "$INSTALLED" -eq 1 ]; then
    CENTER=(nexus-center)
else
    export PYTHONPATH="$REPO_ROOT/command-center/backend:$REPO_ROOT/command-center/frontend${PYTHONPATH:+:$PYTHONPATH}"
    CENTER=(python3 -m nexus_center)
fi
if [ -z "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]; then
    export QT_QPA_PLATFORM=offscreen
fi

OUT_DIR="$REPO_ROOT/build/benchmarks"
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/$(hostname)-$(date +%Y%m%d-%H%M%S).json"
WORK="$(mktemp -d)"
trap 'rm -rf -- "$WORK"' EXIT

for i in $(seq 1 "$RUNS"); do
    "${CENTER[@]}" --benchmark "$IDLE" --no-visit --page overview > "$WORK/launch-$i.json"
    "${CENTER[@]}" --benchmark "$IDLE" > "$WORK/all-$i.json"
done
before=$(pgrep -c -u "$(id -u)" -f "nexus_center|nexus-center" || true)

python3 - "$WORK" "$RUNS" "$OUT" "$before" <<'PY'
import json, os, platform, shutil, statistics, subprocess, sys
work, runs, out, leftover = sys.argv[1], int(sys.argv[2]), sys.argv[3], int(sys.argv[4] or 0)
def load(prefix):
    return [json.load(open(os.path.join(work, f"{prefix}-{i}.json"))) for i in range(1, runs + 1)]
launch, full = load("launch"), load("all")
med = lambda rows, key: statistics.median(r[key] for r in rows)
pages = {}
for r in full:
    for k, v in r["timings_ms"].items():
        if k.startswith(("page:", "controller:")):
            pages.setdefault(k, []).append(v)
def active(unit):
    r = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True)
    return r.stdout.strip() or "unknown"
cpu = next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), platform.processor())
report = {
    "host": {"cpu": cpu, "cpus": os.cpu_count(), "kernel": platform.release(),
             "memory_gib": round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2**30, 1),
             "qpa": os.environ.get("QT_QPA_PLATFORM", "native")},
    "runs": runs,
    "plain_launch": {"startup_to_window_ms": med(launch, "startup_to_window_ms"), "idle_rss_mib": med(launch, "idle_rss_mib"),
                     "idle_cpu_percent": med(launch, "idle_cpu_percent"), "threads": med(launch, "threads")},
    "after_all_modules": {"idle_rss_mib": med(full, "idle_rss_mib"), "idle_cpu_percent": med(full, "idle_cpu_percent"),
                          "threads": med(full, "threads")},
    "load_ms_median": {k: statistics.median(v) for k, v in sorted(pages.items())},
    "leftover_processes": leftover,
    "services_during_run": {u: active(u) for u in ("docker.service", "ollama.service", "nexusos-agent.service")},
    "qml_warnings": sorted({w for r in full for w in r["qml_warnings"]}),
}
json.dump(report, open(out, "w"), indent=2)
print(json.dumps(report, indent=2))
PY
echo "report: $OUT"
