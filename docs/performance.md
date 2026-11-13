# Performance and resource policy

The Command Center must make the OS easier to manage without making it heavier. This
document defines the budgets and records **measured** numbers. Nothing here is estimated.

## Budgets (target: NexusOS on a Plasma 6 Wayland session)

| Metric | Budget | Notes |
|--------|--------|-------|
| Startup to first window (warm) | ≤ 1.0 s | Ryzen 9 9900X class; ≤ 2.0 s on a 4-core laptop |
| Idle RSS after launch (Overview) | ≤ 180 MiB | includes Qt Quick, PySide6, Python |
| Idle RSS after opening every module | ≤ 250 MiB | controllers stay cached, pages unloaded |
| Idle CPU, Command Center visible | ≤ 0.5 % | Overview polling at 5 s |
| Idle CPU, minimised / non-polling page | ≈ 0 % | timers stop on page change |
| Page load | ≤ 150 ms | per module, first open |
| Persistent background services added | 0 | agent is socket-activated, exits after 120 s idle |
| Processes left after quitting | 0 | measured by the benchmark |

## How to measure

```bash
scripts/benchmarks/command-center.sh --runs 3 --idle 20             # from a checkout
scripts/benchmarks/command-center.sh --installed --runs 5 --idle 30 # installed package, in the VM
```

Writes `build/benchmarks/<host>-<timestamp>.json` with medians of: plain launch (Overview),
all-modules visit, per-module controller/page load times, leftover processes, and whether
Docker/Ollama/the agent were running. Use a real Wayland session for representative
numbers; without a display the script uses `QT_QPA_PLATFORM=offscreen` (software rendering).

## Measured results

### Development container (2026-11-13)

Intel Xeon @ 2.10 GHz, 4 vCPU, 15.7 GiB, kernel 6.18, Python 3.13, PySide6 6.12 (pip),
`offscreen` platform, Docker daemon running with no containers, Ollama absent. 3 runs, medians.

| Metric | Result | Budget |
|--------|--------|--------|
| Startup to window (plain launch) | **508 ms** | ≤ 1.0 s ✔ |
| Idle RSS, plain launch | **131.5 MiB** | ≤ 180 MiB ✔ |
| Idle CPU, plain launch (10 s) | **0.29 %** | ≤ 0.5 % ✔ |
| Threads, plain launch | 3 | — |
| Idle RSS after all 14 modules | **149.9 MiB** | ≤ 250 MiB ✔ |
| Idle CPU after all modules | **0.31 %** | ≤ 0.5 % ✔ |
| Page load (first open) | **5 – 39 ms** (Terminal & SSH slowest) | ≤ 150 ms ✔ |
| Controller import | 0.7 – 14 ms; Overview 160 ms (first backend import) | — |
| Leftover processes | 0 | 0 ✔ |

### Ubuntu 26.04 container with the built packages (2026-11-13)

Same host, `ubuntu:26.04`, distribution PySide6 and Python 3.14, packages installed with
APT, `offscreen`, Docker and Ollama **not installed**, all 14 modules visited, 10 s idle
(`build/integration/benchmark-container.json`):

| Metric | Result |
|--------|--------|
| Startup to window | **646 ms** |
| Idle RSS after all modules | **177.5 MiB** |
| Idle CPU | **0.42 %** |
| Threads | 4 |
| Page loads | 7 – 68 ms |

### Not yet measured

* A real Plasma 6 Wayland session (GPU-accelerated Qt Quick) — run the benchmark in the VM.
* The target Ryzen 9 9900X workstation.
* Long-running sessions (memory growth over hours).

## Design rules that keep it light

1. One process; QML pages load on demand through a single `Loader`.
2. Module controllers import their backend on first use.
3. Timers run only for the visible page; intervals are configurable (1–60 s).
4. Expensive data (package catalogue, updates) is cached and refreshed on request.
5. Docker stats are one-shot on demand; container lists poll at 10 s only while visible.
6. The agent is socket-activated with a 120 s idle exit; `TaskRunner` threads expire after 10 s idle.
7. No QtWebEngine is loaded; application UIs open in the existing browser.
8. All histories have hard row limits; logs shown in the UI are bounded.
