# Final results (manuscript dataset)

One 2-vCPU virtual machine (Intel Xeon @ 2.10 GHz), loopback, no network emulation. Gateway on a dedicated
core (GOMAXPROCS=1); backend and load generator share the other core.

- `closed/` — closed loop: C0–C3 × payload 128/1,024/4,096 B × 10/50/100 clients × 6 repetitions (20 s windows),
  plus the C3 batch grid (`*_C3grid_*`, 50 clients, 6 repetitions)
- `open/` — open loop: 250–2,000 req/s, 128 B, 3 repetitions (15 s windows)
- `headroom/` — metadata headroom test (0–7,500 B filler headers)
- `microbench_go.json`, `microbench_openssl.json` — signature cost per operation
- `crosscheck.txt` — ML-DSA-65 cross-check against OpenSSL (200 cases)
- `summary/` — CSV tables, statistical tests, `results.json`
- `figures/` — manuscript figures
- `report.html` — results page (open in a browser)
- `logs.zip` — gateway/backend/load-generator logs for every run

Regenerate: `python3 analysis/summarize.py results/final --microbench results/final/microbench_*.json`
and `python3 analysis/paper_figures.py results/final results/final/figures`.
