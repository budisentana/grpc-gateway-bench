"""Figures for the JACOST manuscript (single-column width, print-friendly).

Usage: python3 analysis/paper_figures.py RESULTS_DIR OUT_DIR
Reads RESULTS_DIR/summary/{summary.csv,runs.csv,headroom.csv}.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import pandas as pd

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Liberation Serif", "TeX Gyre Termes", "DejaVu Serif"],
    "font.size": 7, "axes.titlesize": 7, "axes.labelsize": 7, "legend.fontsize": 6.5,
    "xtick.labelsize": 6.5, "ytick.labelsize": 6.5, "axes.linewidth": 0.6,
    "lines.linewidth": 1.0, "savefig.dpi": 300,
})
W = 3.15  # inches, one JACOST column
CFG = ["C0", "C1", "C2", "C3"]
COL = {"C0": "#4d4d4d", "C1": "#1b9e9e", "C2": "#d95f02", "C3": "#6a51a3"}
HATCH = {"C0": "", "C1": "////", "C2": "....", "C3": "xxxx"}
MARK = {"C0": "o", "C1": "s", "C2": "^", "C3": "D"}


def fig_architecture(out):
    fig, ax = plt.subplots(figsize=(W, 2.0))
    ax.set_xlim(0, 100); ax.set_ylim(0, 60); ax.axis("off")

    def box(x, y, w, h, text, fc="white", lw=0.7, fs=6, bold=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=1.5", fc=fc, ec="black", lw=lw))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, weight="bold" if bold else "normal")

    def arrow(x1, y1, x2, y2):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="-|>", lw=0.7, color="black", mutation_scale=6, shrinkA=0, shrinkB=0))

    # client
    box(0, 38, 25, 13, "REST client\nJSON, HTTP/1.1", fs=5.6)
    ax.text(12.5, 31, "public link:\nTLS 1.3 with\nX25519MLKEM768", ha="center", va="center", fontsize=5.3)
    # gateway
    ax.add_patch(FancyBboxPatch((28, 1), 44, 58, boxstyle="round,pad=0,rounding_size=2", fc="#efefef", ec="black", lw=0.7))
    ax.text(50, 54.5, "Translation gateway", ha="center", va="center", fontsize=6.5, weight="bold")
    steps = ["1. Terminate public TLS", "2. Map JSON to Protobuf", "3. Authenticate (C0-C3)", "4. Forward over HTTP/2"]
    ys = [41, 29, 17, 5]
    for st, y in zip(steps, ys):
        hi = st.startswith("3")
        box(31, y, 38, 8.5, st, fc="#d9d2e9" if hi else "white", lw=1.1 if hi else 0.7)
    for y1, y2 in zip(ys[:-1], ys[1:]):
        arrow(50, y1, 50, y2 + 8.5)
    arrow(25, 44.5, 31, 44.5)
    # service
    box(78, 3, 22, 13, "gRPC service\n(verifies)")
    arrow(69, 9.25, 78, 9.25)
    ax.text(89, 33, "internal link:\nmTLS, X25519\n(C1: X25519MLKEM768)\n+ signature (C2)\nor batch proof (C3)",
            ha="center", va="center", fontsize=5.3)
    fig.savefig(out, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def fig_closed(s, out, payload=128):
    d = s[(s["mode"] == "closed") & (s["payload"] == payload) & (s["pad_bytes"] == 0)]
    conc = sorted(d["concurrency"].dropna().unique())
    fig, axes = plt.subplots(2, 1, figsize=(W, 3.0), sharex=True)
    bw = 0.2
    for ax, metric, lo, hi, lab in [(axes[0], "rps", "rps_ci_lo", "rps_ci_hi", "Throughput (req/s)"),
                                    (axes[1], "lat_p99_ms", "lat_p99_ms_ci_lo", "lat_p99_ms_ci_hi", "p99 latency (ms)")]:
        for i, cfg in enumerate(CFG):
            r = d[d["config"] == cfg].set_index("concurrency").reindex(conc)
            xs = [j + (i - 1.5) * bw for j in range(len(conc))]
            err = [(r[metric] - r[lo]).clip(lower=0).fillna(0), (r[hi] - r[metric]).clip(lower=0).fillna(0)]
            ax.bar(xs, r[metric], bw * 0.92, color=COL[cfg], hatch=HATCH[cfg], edgecolor="white", lw=0.3, label=cfg,
                   yerr=err, error_kw=dict(lw=0.6, capsize=1.5, capthick=0.6))
        ax.set_ylabel(lab)
        ax.grid(axis="y", lw=0.3, alpha=0.6)
        ax.set_axisbelow(True)
        for sp in ["top", "right"]:
            ax.spines[sp].set_visible(False)
    axes[1].set_xticks(range(len(conc)))
    axes[1].set_xticklabels([f"{int(c)} clients" for c in conc])
    axes[0].legend(ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.22), handlelength=1.2, columnspacing=1.0)
    fig.tight_layout(h_pad=0.4)
    fig.savefig(out, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def fig_open(s, out):
    d = s[(s["mode"] == "open")]
    fig, ax = plt.subplots(figsize=(W, 1.9))
    for cfg in CFG:
        r = d[d["config"] == cfg].sort_values("offered_rate")
        if r.empty:
            continue
        ax.plot(r["offered_rate"], r["lat_p99_ms"], marker=MARK[cfg], ms=3, color=COL[cfg], label=cfg)
    ax.set_yscale("log")
    ax.set_xlabel("Offered load (req/s)")
    ax.set_ylabel("p99 latency (ms, log scale)")
    ax.grid(lw=0.3, alpha=0.6, which="major")
    for sp in ["top", "right"]:
        ax.spines[sp].set_visible(False)
    ax.legend(ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, 1.18), handlelength=1.5, columnspacing=1.0)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def fig_headroom(h, out):
    fig, ax = plt.subplots(figsize=(W, 1.9))
    for cfg in ["C0", "C2", "C3"]:
        r = h[h["config"] == cfg].sort_values("pad_bytes")
        if r.empty:
            continue
        ok = r["completed_ok"] > 0
        ax.plot(r["pad_bytes"], r["metadata_bytes_max"], color=COL[cfg], lw=0.9, label=cfg)
        ax.scatter(r.loc[ok, "pad_bytes"], r.loc[ok, "metadata_bytes_max"], s=9, color=COL[cfg], marker=MARK[cfg], zorder=3)
        ax.scatter(r.loc[~ok, "pad_bytes"], r.loc[~ok, "metadata_bytes_max"], s=11, facecolor="white", edgecolor=COL[cfg],
                   marker=MARK[cfg], lw=0.8, zorder=3)
    ax.axhline(8192, color="black", ls="--", lw=0.7)
    ax.text(ax.get_xlim()[1] * 0.99 if ax.get_xlim()[1] else 7000, 8192 + 250, "8,192-byte limit", ha="right", fontsize=6)
    ax.set_xlabel("Additional metadata (bytes)")
    ax.set_ylabel("Header list size (bytes)")
    ax.grid(lw=0.3, alpha=0.6)
    for sp in ["top", "right"]:
        ax.spines[sp].set_visible(False)
    ax.legend(ncol=3, frameon=False, loc="upper left", handlelength=1.5)
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def main():
    res, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    import json
    data = json.load(open(os.path.join(res, "summary", "results.json")))
    default = pd.DataFrame(data["summary"])  # excludes the C3 grid and headroom runs
    fig_architecture(os.path.join(out, "fig1_architecture.png"))
    fig_closed(default, os.path.join(out, "fig2_closed.png"))
    fig_open(default, os.path.join(out, "fig3_open.png"))
    hp = os.path.join(res, "summary", "headroom.csv")
    if os.path.exists(hp):
        fig_headroom(pd.read_csv(hp), os.path.join(out, "fig4_headroom.png"))
    print("figures written to", out)


if __name__ == "__main__":
    main()
