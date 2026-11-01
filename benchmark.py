"""
Full benchmark: block-size sweep + evaluation of the adaptive selector.

    python benchmark.py                       # 50/100/200 MB, 30 runs  (about 10-20 min)
    python benchmark.py --quick               # smoke test (about 1 min)
    python benchmark.py --threads 1 4         # also the parallel implementation
    python benchmark.py --variant update      # ablation: no B||PRG concatenation copy

Outputs (prefix --out, default results/results):
    *_raw.csv        every timed run (interleaved, randomised order each round)
    *_summary.csv    mean, SD, median, 95% bootstrap CI, MB/s per (file size, threads, block size)
    *_adaptive.csv   every calibration trial: chosen size, calibration cost, regret vs the sweep
    *_report.md      paper-ready tables and key findings
    *_plot_t*.png    block-size curves (if matplotlib is installed)
"""
import argparse
import collections
import csv
import os
import platform
import random
import secrets
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

from adaptive import APPROVED_KB, select_block_size
from pow_core import KB, MB, prove_with

FIXED_DEFAULTS_KB = (4, 64, 256, 1024)


def make_file(path, size_mb):
    with open(path, "wb") as f:
        for _ in range(size_mb):
            f.write(os.urandom(MB))


def read_through(path):
    with open(path, "rb") as f:
        while f.read(8 * MB):
            pass


def boot_ci(xs, n=2000):
    rng = random.Random(1)
    means = sorted(statistics.fmean(rng.choices(xs, k=len(xs))) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n)]


def env_info():
    info = collections.OrderedDict()
    info["OS"] = platform.platform()
    info["Processor"] = platform.processor() or "n/a"
    info["Logical CPUs"] = os.cpu_count()
    info["Python"] = platform.python_version()
    try:
        out = subprocess.run(["lscpu"], capture_output=True, text=True, timeout=5).stdout
        for line in out.splitlines():
            if line.split(":")[0].strip() in ("Model name", "L1d cache", "L2 cache", "L3 cache"):
                info[line.split(":")[0].strip()] = line.split(":", 1)[1].strip()
    except Exception:
        info["Cache sizes"] = "fill in from Task Manager > Performance > CPU"
    return info


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def timed(fn):
    t = time.perf_counter()
    r = fn()
    return r, time.perf_counter() - t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[50, 100, 200])
    ap.add_argument("--blocks", type=int, nargs="+", default=[4, 16, 32, 64, 128, 256, 512, 1024])
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--threads", type=int, nargs="+", default=[1])
    ap.add_argument("--variant", choices=["concat", "update"], default="concat")
    ap.add_argument("--adaptive-trials", type=int, default=10)
    ap.add_argument("--sample-mb", type=float, default=16)
    ap.add_argument("--calib-rounds", type=int, default=5)
    ap.add_argument("--tol", type=float, default=0.05)
    ap.add_argument("--out", default=os.path.join("results", "results"))
    ap.add_argument("--dir", default=None, help="folder for the temporary test files")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    if a.quick:
        a.sizes, a.blocks, a.runs, a.adaptive_trials, a.sample_mb, a.calib_rounds = [8], [16, 64, 256], 3, 3, 2, 2
    if os.path.dirname(a.out):
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
    cand = [b for b in APPROVED_KB if b in a.blocks]  # candidates the selector may choose from
    t_adapt = a.threads[0]

    print("python %s | variant=%s | runs=%d | threads=%s | sizes=%s MB" % (
        platform.python_version(), a.variant, a.runs, a.threads, a.sizes))
    print("Tip: plug in the charger, close other apps, do not touch the laptop while this runs.\n")

    tmp = tempfile.mkdtemp(dir=a.dir)
    raw, adaptive_rows = [], []
    try:
        for size in a.sizes:
            cp, sp = os.path.join(tmp, "c%d.bin" % size), os.path.join(tmp, "s%d.bin" % size)
            make_file(cp, size)
            shutil.copyfile(cp, sp)
            read_through(cp); read_through(sp)
            configs = [(b, t) for b in a.blocks for t in a.threads]
            for b, t in configs:  # untimed warm-up
                prove_with(cp, secrets.token_bytes(32), b * KB, t, variant=a.variant)
            for rnd in range(1, a.runs + 1):
                random.shuffle(configs)
                for b, t in configs:
                    seed = secrets.token_bytes(32)
                    rc, tg = timed(lambda: prove_with(cp, seed, b * KB, t, variant=a.variant))
                    rs, tv = timed(lambda: prove_with(sp, seed, b * KB, t, variant=a.variant))
                    raw.append(dict(file_mb=size, threads=t, block_kb=b, run=rnd, gen_s=tg, ver_s=tv, match=int(rc == rs)))
                if rnd % 5 == 0 or rnd == a.runs:
                    print("  %d MB sweep: round %d/%d" % (size, rnd, a.runs))
            # adaptive trials (calibration is random, so repeat it)
            for k in range(1, a.adaptive_trials + 1):
                info = select_block_size(cp, cand, t_adapt, a.sample_mb, a.calib_rounds, a.tol, None, True, a.variant)
                adaptive_rows.append(dict(file_mb=size, trial=k, chosen_kb=info["chosen_kb"],
                                          calibration_s=info["calibration_s"]))
            print("  %d MB adaptive: chosen %s" % (size, sorted(r["chosen_kb"] for r in adaptive_rows if r["file_mb"] == size)))
            os.remove(cp); os.remove(sp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # ---------------- summaries
    summ = {}
    for size in a.sizes:
        for t in a.threads:
            for b in a.blocks:
                sel = [r for r in raw if r["file_mb"] == size and r["threads"] == t and r["block_kb"] == b]
                g, v = [r["gen_s"] for r in sel], [r["ver_s"] for r in sel]
                lo, hi = boot_ci(g)
                summ[(size, t, b)] = dict(
                    file_mb=size, threads=t, block_kb=b, n=len(g), gen_mean=statistics.fmean(g),
                    gen_sd=statistics.stdev(g) if len(g) > 1 else 0.0, gen_median=statistics.median(g),
                    gen_ci_lo=lo, gen_ci_hi=hi, ver_mean=statistics.fmean(v),
                    ver_sd=statistics.stdev(v) if len(v) > 1 else 0.0, gen_MBps=size / statistics.fmean(g),
                    all_match=int(all(r["match"] for r in sel)))
    for r in adaptive_rows:
        s = summ[(r["file_mb"], t_adapt, r["chosen_kb"])]
        best = min(summ[(r["file_mb"], t_adapt, b)]["gen_mean"] for b in a.blocks)
        r["chosen_mean_s"], r["best_mean_s"], r["regret"] = s["gen_mean"], best, s["gen_mean"] / best

    def dump(path, rows):
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    dump(a.out + "_raw.csv", raw)
    dump(a.out + "_summary.csv", list(summ.values()))
    dump(a.out + "_adaptive.csv", adaptive_rows)

    # ---------------- report
    L = ["# PoW block-size benchmark report", "", "## Environment", ""]
    L += ["- %s: %s" % (k, v) for k, v in env_info().items()]
    L += ["- Variant: %s; runs per setting: %d; block order randomised every round; warm file cache; "
          "client and server copies are separate local files; no network." % (a.variant, a.runs), ""]
    findings = []
    for t in a.threads:
        for size in a.sizes:
            part = [summ[(size, t, b)] for b in a.blocks]
            best = min(part, key=lambda s: s["gen_mean"])
            L += ["## Block-size sweep: %d MB, threads = %d" % (size, t), ""]
            rows = [[("**%d**" % s["block_kb"]) if s is best else s["block_kb"],
                     (size * MB) // (s["block_kb"] * KB),
                     "%.4f +/- %.4f" % (s["gen_mean"], s["gen_sd"]),
                     "[%.4f, %.4f]" % (s["gen_ci_lo"], s["gen_ci_hi"]),
                     "%.4f +/- %.4f" % (s["ver_mean"], s["ver_sd"]),
                     "%.0f" % s["gen_MBps"], "yes" if s["all_match"] else "NO"] for s in part]
            L += [md_table(["Block (KB)", "Blocks N", "Generation (s) mean +/- SD", "95% CI (gen.)",
                            "Verification (s) mean +/- SD", "Gen. MB/s", "Proofs match"], rows), ""]
            def sp(b):
                return summ[(size, t, b)]["gen_mean"] / best["gen_mean"] if (size, t, b) in summ else None
            txt = "%d MB, %d thread(s): fastest block size = %d KB (%.4f s, %.0f MB/s)" % (
                size, t, best["block_kb"], best["gen_mean"], best["gen_MBps"])
            for b in (4, 64, 256, 1024):
                if sp(b) and b != best["block_kb"]:
                    txt += "; %.2fx faster than %d KB" % (sp(b), b)
            findings.append(txt)
    L += ["## Adaptive block-size selection (threads = %d)" % t_adapt, "",
          "Calibration: %.0f MB prefix, %d timed rounds (+1 warm-up), median per candidate, tolerance %.0f%% "
          "(smallest block size within tolerance of the fastest). Candidates: %s KB. Regret = mean generation time at the "
          "chosen size / mean at the true best size of the sweep." % (a.sample_mb, a.calib_rounds, a.tol * 100, cand), ""]
    rows = []
    for size in a.sizes:
        tr = [r for r in adaptive_rows if r["file_mb"] == size]
        best_b = min(a.blocks, key=lambda b: summ[(size, t_adapt, b)]["gen_mean"])
        chosen = collections.Counter(r["chosen_kb"] for r in tr)
        mode = chosen.most_common(1)[0][0]
        regrets = [r["regret"] for r in tr]
        calib = statistics.fmean(r["calibration_s"] for r in tr)
        row = [size, best_b, ", ".join("%d KB x%d" % kv for kv in sorted(chosen.items())),
               "%.3f (max %.3f)" % (statistics.fmean(regrets), max(regrets)), "%.2f" % calib]
        for d in FIXED_DEFAULTS_KB:
            if d in a.blocks:
                row.append("%.2fx" % (summ[(size, t_adapt, d)]["gen_mean"] / statistics.fmean(r["chosen_mean_s"] for r in tr)))
        rows.append(row)
        findings.append("%d MB: adaptive selector chose %s (true best: %d KB); mean regret %.3f; calibration %.2f s." % (
            size, dict(sorted(chosen.items())), best_b, statistics.fmean(regrets), calib))
    L += [md_table(["File (MB)", "True best (KB)", "Chosen over %d trials" % a.adaptive_trials, "Regret mean (max)",
                    "Calibration (s)"] + ["Speed-up vs fixed %d KB" % d for d in FIXED_DEFAULTS_KB if d in a.blocks], rows), ""]
    be = []
    for size in a.sizes:
        tr = [r for r in adaptive_rows if r["file_mb"] == size]
        cm = statistics.fmean(r["chosen_mean_s"] for r in tr)
        cs = statistics.fmean(r["calibration_s"] for r in tr)
        for d in FIXED_DEFAULTS_KB:
            if d in a.blocks:
                gain = summ[(size, t_adapt, d)]["gen_mean"] - cm
                be.append([size, "%d KB" % d, "%.4f" % gain, ("%.1f" % (cs / gain)) if gain > 0 else "never (fixed size is not slower)"])
    L += ["### Break-even: PoW runs needed before one calibration pays for itself", "",
          md_table(["File (MB)", "Fixed default", "Time saved per PoW (s)", "PoWs to break even"], be), ""]
    L += ["## Key findings (copy into the paper after checking them)", ""] + ["- " + f for f in findings] + [""]
    with open(a.out + "_report.md", "w") as f:
        f.write("\n".join(L))

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for t in a.threads:
            plt.figure(figsize=(6.5, 4.2))
            for size in a.sizes:
                p = [summ[(size, t, b)] for b in a.blocks]
                plt.errorbar([s["block_kb"] for s in p], [s["gen_mean"] for s in p], yerr=[s["gen_sd"] for s in p],
                             marker="o", capsize=3, label="%d MB" % size)
            plt.xscale("log", base=2); plt.xlabel("Block size (KB)"); plt.ylabel("Proof generation time (s)")
            plt.title("Block-size sweep (threads=%d, %d runs, mean +/- SD)" % (t, a.runs))
            plt.grid(alpha=.3); plt.legend(); plt.tight_layout()
            plt.savefig("%s_plot_t%d.png" % (a.out, t), dpi=200); plt.close()
    except ImportError:
        print("matplotlib not installed: plots skipped (pip install matplotlib)")

    print("\n" + "\n".join(L))
    print("\nSaved: %s_raw.csv, _summary.csv, _adaptive.csv, _report.md" % a.out)
    if not all(r["match"] for r in raw):
        print("WARNING: some client/server proofs did not match!")
        sys.exit(1)


if __name__ == "__main__":
    main()
