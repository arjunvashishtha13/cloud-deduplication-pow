"""
Adaptive block-size selection.

The best block size depends on the client (cache hierarchy, CPU, runtime). The client runs a
short calibration on a prefix of the file, measuring each server-approved candidate in
randomised rounds (first round discarded as warm-up), takes the median per candidate and picks
the smallest block size whose median is within `tol` of the fastest (smaller = less memory).
"""
import json
import os
import platform
import random
import statistics
import time

from pow_core import KB, MB, prove_with

APPROVED_KB = (16, 32, 64, 128, 256, 512, 1024)
DEFAULT_SAMPLE_MB = 16
DEFAULT_ROUNDS = 5
DEFAULT_TOL = 0.05


def platform_fingerprint():
    return "|".join([platform.system(), platform.machine(), platform.processor() or "-",
                     platform.python_version(), str(os.cpu_count())])


def size_class(file_size):
    if file_size < 32 * MB:
        return "small"
    if file_size < 256 * MB:
        return "medium"
    return "large"


def _load(cache_path):
    try:
        with open(cache_path, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(cache_path, cache):
    try:
        with open(cache_path, "w") as f:
            json.dump(cache, f, indent=2)
    except OSError:
        pass


def select_block_size(path, candidates_kb=APPROVED_KB, threads=1, sample_mb=DEFAULT_SAMPLE_MB,
                      rounds=DEFAULT_ROUNDS, tol=DEFAULT_TOL, cache_path=None, force=False,
                      variant="concat"):
    size = os.path.getsize(path)
    key = "%s|t%d|%s" % (platform_fingerprint(), threads, size_class(size))
    if cache_path and not force:
        hit = _load(cache_path).get(key)
        if hit:
            out = dict(hit)
            out.update(from_cache=True, calibration_s=0.0)
            return out

    sample = min(size, int(sample_mb * MB))
    cands = [c for c in sorted(set(candidates_kb)) if 2 * c * KB <= sample]
    if not cands:  # tiny file: calibration is meaningless, pick the smallest approved size
        return dict(chosen_kb=min(candidates_kb), scores={}, calibration_s=0.0, from_cache=False,
                    note="file too small to calibrate")

    t0 = time.perf_counter()
    times = {c: [] for c in cands}
    for rnd in range(rounds + 1):  # round 0 = warm-up (discarded)
        order = cands[:]
        random.shuffle(order)
        for c in order:
            seed = os.urandom(32)
            t = time.perf_counter()
            prove_with(path, seed, c * KB, threads, max_bytes=sample, variant=variant)
            dt = time.perf_counter() - t
            if rnd > 0:
                times[c].append(dt)
    scores = {c: statistics.median(v) for c, v in times.items()}
    best = min(scores.values())
    chosen = min(c for c in cands if scores[c] <= best * (1 + tol))
    out = dict(chosen_kb=chosen, scores={str(k): v for k, v in scores.items()},
               calibration_s=time.perf_counter() - t0, from_cache=False)
    if cache_path:
        cache = _load(cache_path)
        cache[key] = dict(chosen_kb=chosen, scores=out["scores"])
        _save(cache_path, cache)
    return out
