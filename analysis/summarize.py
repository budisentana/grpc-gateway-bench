"""Summarise run JSON files into CSV tables, statistical tests and figures.

Usage: python3 analysis/summarize.py RESULTS_DIR [--out OUT_DIR]

Outputs (in OUT_DIR, default RESULTS_DIR/summary):
  runs.csv               one row per run (all metrics)
  summary.csv            median across repetitions + 95% bootstrap CI
  table7_translation.csv gateway stage times for C0 (paper Table 7)
  table8_bytes.csv       metadata and bytes per request (Table 8)
  table9_throughput.csv  throughput / latency / CPU per configuration (Table 9)
  table10_batch.csv      C3 batch grid (Table 10)
  headroom.csv           metadata headroom runs, if present
  stats_tests.csv        Kruskal-Wallis + Holm-corrected Mann-Whitney U
  fig_p99_vs_load.png, fig_throughput_vs_load.png
  results.json           compact data for the results web page
"""
import argparse
import glob
import itertools
import json
import os

import numpy as np
import pandas as pd
from scipy import stats as sps

CONFIG_ORDER = ["C0", "C1", "C2", "C3"]


def load_runs(d):
    rows = []
    for path in sorted(glob.glob(os.path.join(d, "**", "*.json"), recursive=True)):
        if os.sep + "summary" + os.sep in path:
            continue
        try:
            r = json.load(open(path))
        except Exception:
            continue
        if "latency" not in r or "gateway" not in r:
            continue
        g, b = r.get("gateway") or {}, r.get("backend") or {}
        dur = r["duration_s"]
        ok = r["completed_ok"]
        reqs = max(g.get("requests", 0), 1)
        lat = r["latency"]
        errs = sum((r.get("errors") or {}).values())
        rows.append({
            "file": os.path.relpath(path, d),
            "label": r.get("label", ""),
            "config": g.get("config"),
            "mode": r["mode"],
            "concurrency": r.get("concurrency", np.nan),
            "offered_rate": r.get("offered_rate", np.nan),
            "payload": r["payload_bytes"],
            "rep": r.get("rep", 1),
            "batch_window_ms": g.get("batch_window_ms"),
            "batch_max": g.get("batch_max"),
            "pad_bytes": g.get("pad_bytes", 0),
            "sig_backend": g.get("sig_backend", ""),
            "duration_s": dur,
            "completed_ok": ok,
            "errors": errs,
            "error_rate_pct": 100 * errs / max(ok + errs, 1),
            "dropped": r.get("dropped", 0),
            "rps": r["throughput_rps"],
            "lat_mean_ms": lat["mean_us"] / 1000,
            "lat_p50_ms": lat["p50_us"] / 1000,
            "lat_p95_ms": lat["p95_us"] / 1000,
            "lat_p99_ms": lat["p99_us"] / 1000,
            "lat_max_ms": lat["max_us"] / 1000,
            "gw_cpu_pct": 100 * g.get("cpu_seconds", 0) / dur,
            "gw_cpu_us_per_req": 1e6 * g.get("cpu_seconds", 0) / reqs,
            "gw_rss_mb": g.get("rss_mb"),
            "gw_gomaxprocs": g.get("gomaxprocs"),
            "be_cpu_pct": 100 * b.get("cpu_seconds", 0) / dur,
            "stage_parse_us": g.get("stage_parse", {}).get("p50_us"),
            "stage_map_us": g.get("stage_map", {}).get("p50_us"),
            "stage_auth_us": g.get("stage_auth", {}).get("p50_us"),
            "stage_auth_p99_us": g.get("stage_auth", {}).get("p99_us"),
            "stage_forward_us": g.get("stage_forward", {}).get("p50_us"),
            "stage_total_us": g.get("stage_total", {}).get("p50_us"),
            # prefer what the backend actually received (includes headers the HTTP/2 client adds)
            "metadata_bytes_avg": b.get("metadata_bytes_avg_received") or g.get("metadata_bytes_avg"),
            "metadata_bytes_max": b.get("metadata_bytes_max_received") or g.get("metadata_bytes_max"),
            "metadata_source": "backend" if b.get("metadata_bytes_avg_received") else "gateway",
            "internal_bytes_out_per_req": g.get("internal_bytes_out", 0) / reqs,
            "public_bytes_in_per_req": g.get("public_bytes_in", 0) / reqs,
            "signatures_per_req": g.get("signatures", 0) / reqs,
            "avg_batch_size": (g.get("batched_requests", 0) / g["batches"]) if g.get("batches") else np.nan,
            "be_verify_p50_us": (b.get("verify") or {}).get("p50_us"),
            "be_metadata_rejects": (b.get("counters") or {}).get("metadata_too_large", 0),
            "new_connections": r.get("new_connections"),
        })
    return pd.DataFrame(rows)


def boot_ci(x, n=2000, seed=1):
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x)]
    if len(x) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    meds = np.median(rng.choice(x, size=(n, len(x)), replace=True), axis=1)
    return (float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5)))


GROUP = ["label", "config", "mode", "concurrency", "offered_rate", "payload", "batch_window_ms", "batch_max", "pad_bytes"]
METRICS = ["rps", "lat_p50_ms", "lat_p95_ms", "lat_p99_ms", "error_rate_pct", "gw_cpu_pct", "gw_cpu_us_per_req",
           "gw_rss_mb", "stage_parse_us", "stage_map_us", "stage_auth_us", "stage_forward_us", "stage_total_us",
           "metadata_bytes_avg", "internal_bytes_out_per_req", "public_bytes_in_per_req", "signatures_per_req",
           "avg_batch_size", "be_verify_p50_us"]


def summarise(df):
    out = []
    for key, g in df.groupby(GROUP, dropna=False):
        row = dict(zip(GROUP, key))
        row["reps"] = len(g)
        for m in METRICS:
            row[m] = float(np.nanmedian(g[m])) if g[m].notna().any() else np.nan
        for m in ["rps", "lat_p99_ms"]:
            lo, hi = boot_ci(g[m])
            row[m + "_ci_lo"], row[m + "_ci_hi"] = lo, hi
        out.append(row)
    s = pd.DataFrame(out)
    s["config"] = pd.Categorical(s["config"], CONFIG_ORDER + sorted(set(s["config"]) - set(CONFIG_ORDER)))
    return s.sort_values(["label", "mode", "config", "payload", "concurrency", "offered_rate"])


def holm(pvals):
    order = np.argsort(pvals)
    m = len(pvals)
    adj = np.empty(m)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * pvals[i])
        adj[i] = min(1.0, running)
    return adj


def tests(df):
    rows = []
    main = df[(df["pad_bytes"] == 0) & df["config"].isin(CONFIG_ORDER)]
    main = main[~((main["config"] == "C3") & main["file"].str.contains("C3grid"))]
    keys = ["label", "mode", "concurrency", "offered_rate", "payload"]
    for key, g in main.groupby(keys, dropna=False):
        for metric in ["rps", "lat_p99_ms"]:
            groups = {c: g.loc[g["config"] == c, metric].dropna().values for c in CONFIG_ORDER}
            groups = {c: v for c, v in groups.items() if len(v) >= 2}
            if len(groups) < 2:
                continue
            try:
                kw = sps.kruskal(*groups.values())
                kw_p = kw.pvalue
            except ValueError:
                kw_p = np.nan
            pairs = list(itertools.combinations(groups, 2))
            ps, effs = [], []
            for a, b in pairs:
                u = sps.mannwhitneyu(groups[a], groups[b], alternative="two-sided")
                ps.append(u.pvalue)
                effs.append(2 * u.statistic / (len(groups[a]) * len(groups[b])) - 1)  # rank-biserial; >0 means a > b
            adj = holm(np.array(ps)) if ps else []
            for (a, b), p, pa, e in zip(pairs, ps, adj, effs):
                rows.append(dict(zip(keys, key), metric=metric, kruskal_p=kw_p, pair=f"{a} vs {b}",
                                 mwu_p=p, mwu_p_holm=pa, rank_biserial=e,
                                 n_a=len(groups[a]), n_b=len(groups[b])))
    return pd.DataFrame(rows)


def figures(s, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    main = s[(s["pad_bytes"] == 0) & s["config"].isin(CONFIG_ORDER)]
    for metric, fname, ylabel in [("lat_p99_ms", "fig_p99_vs_load.png", "p99 latency (ms)"),
                                  ("rps", "fig_throughput_vs_load.png", "throughput (RPS)")]:
        for (label, mode, payload), g in main.groupby(["label", "mode", "payload"]):
            x = "concurrency" if mode == "closed" else "offered_rate"
            fig, ax = plt.subplots(figsize=(6, 4))
            for cfg in CONFIG_ORDER:
                c = g[g["config"] == cfg].sort_values(x)
                if c.empty:
                    continue
                ax.plot(c[x], c[metric], marker="o", label=cfg)
                lo, hi = metric + "_ci_lo", metric + "_ci_hi"
                if lo in c and c[lo].notna().any():
                    ax.fill_between(c[x], c[lo], c[hi], alpha=0.15)
            ax.set_xlabel("concurrent clients" if mode == "closed" else "offered load (RPS)")
            ax.set_ylabel(ylabel)
            ax.set_title(f"{label}, {mode} loop, payload {payload} B")
            ax.grid(alpha=0.3)
            ax.legend()
            fig.tight_layout()
            fig.savefig(os.path.join(out, fname.replace(".png", f"_{label}_{mode}_p{payload}.png")), dpi=150)
            plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--out")
    ap.add_argument("--microbench", nargs="*", default=[], help="microbench JSON files to include")
    a = ap.parse_args()
    out = a.out or os.path.join(a.results, "summary")
    os.makedirs(out, exist_ok=True)

    df = load_runs(a.results)
    if df.empty:
        raise SystemExit("no run files found")
    df.to_csv(os.path.join(out, "runs.csv"), index=False)
    s = summarise(df)
    s.to_csv(os.path.join(out, "summary.csv"), index=False)

    is_grid = df["file"].str.contains("C3grid")
    is_head = df["label"] == "headroom"
    main_s = summarise(df[~is_grid & ~is_head]) if (~is_grid & ~is_head).any() else s.iloc[0:0]

    t7 = main_s[(main_s["config"] == "C0") & (main_s["mode"] == "closed")][
        ["label", "payload", "concurrency", "reps", "stage_parse_us", "stage_map_us", "stage_forward_us", "stage_total_us"]]
    t7.to_csv(os.path.join(out, "table7_translation.csv"), index=False)

    t8 = main_s[main_s["mode"] == "closed"].groupby(["label", "config", "payload"], observed=True)[
        ["metadata_bytes_avg", "internal_bytes_out_per_req", "public_bytes_in_per_req", "signatures_per_req"]].median().reset_index()
    t8.to_csv(os.path.join(out, "table8_bytes.csv"), index=False)

    t9 = main_s[["label", "config", "mode", "concurrency", "offered_rate", "payload", "reps", "rps", "rps_ci_lo", "rps_ci_hi",
                 "lat_p50_ms", "lat_p99_ms", "lat_p99_ms_ci_lo", "lat_p99_ms_ci_hi", "error_rate_pct", "gw_cpu_pct",
                 "gw_cpu_us_per_req", "gw_rss_mb", "stage_auth_us"]]
    t9.to_csv(os.path.join(out, "table9_throughput.csv"), index=False)

    grid = summarise(df[is_grid]) if is_grid.any() else pd.DataFrame()
    if not grid.empty:
        c0 = main_s[(main_s["config"] == "C0") & (main_s["mode"] == "closed") & (main_s["payload"] == 128)]
        ref = {}
        for _, r in c0.iterrows():
            ref[(r["label"], r["concurrency"])] = (r["rps"], r["lat_p50_ms"])
        grid["rps_pct_of_C0"] = [100 * r.rps / ref[(r.label, r.concurrency)][0] if (r.label, r.concurrency) in ref else np.nan
                                 for r in grid.itertuples()]
        grid["added_p50_ms_vs_C0"] = [r.lat_p50_ms - ref[(r.label, r.concurrency)][1] if (r.label, r.concurrency) in ref else np.nan
                                      for r in grid.itertuples()]
        grid[["label", "concurrency", "batch_window_ms", "batch_max", "reps", "rps", "rps_pct_of_C0", "lat_p50_ms",
              "added_p50_ms_vs_C0", "lat_p99_ms", "avg_batch_size", "signatures_per_req", "gw_cpu_us_per_req"]].to_csv(
            os.path.join(out, "table10_batch.csv"), index=False)

    head = df[is_head]
    if not head.empty:
        head.sort_values(["config", "pad_bytes"])[["config", "pad_bytes", "metadata_bytes_avg", "metadata_bytes_max",
                                                   "completed_ok", "errors", "be_metadata_rejects"]].to_csv(
            os.path.join(out, "headroom.csv"), index=False)

    t = tests(df[~is_head])
    t.to_csv(os.path.join(out, "stats_tests.csv"), index=False)
    figures(main_s, out)

    micro = []
    for f in a.microbench:
        micro.append(json.load(open(f)))
    compact = {
        "runs": int(len(df)),
        "summary": json.loads(main_s.to_json(orient="records")),
        "batch_grid": json.loads(grid.to_json(orient="records")) if not grid.empty else [],
        "headroom": json.loads(head.sort_values(["config", "pad_bytes"]).to_json(orient="records")) if not head.empty else [],
        "tests": json.loads(t.to_json(orient="records")),
        "microbench": micro,
    }
    with open(os.path.join(out, "results.json"), "w") as fh:
        json.dump(compact, fh, indent=1)
    print(f"{len(df)} runs summarised into {out}")


if __name__ == "__main__":
    main()
