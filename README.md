# Secure cloud deduplication: PoW with adaptive block size (v2)

Tested with Python 3.8+ (standard library only; `matplotlib` optional for plots,
`firebase-admin` optional for the Firebase registry).

## Run order
```
python run_tests.py                   # 1. all correctness/security tests must pass (exit code 0)
python main.py                        # 2. local demo: alice stores, bob verified (adaptive), mallory denied
python benchmark.py                   # 3. MAIN RESULTS: 50/100/200 MB, 30 runs, sweep + adaptive evaluation
python benchmark.py --variant update --sizes 100 --out results/ablation_update   # 4. ablation (no concat copy)
python benchmark.py --sizes 100 --threads 1 4 8 --blocks 16 64 256 1024 --runs 20 --out results/parallel   # 5. optional
python benchmark.py --quick           # 1-minute smoke test
```
Before step 3: charger plugged in, High Performance mode, close other apps, do not touch the laptop.
If the adaptive regret is high, repeat with `--calib-rounds 9 --sample-mb 32`.

## Files
| File | Purpose |
|---|---|
| `pow_core.py` | PoW algorithm (output identical to your old `proof.py`), parallel version, streaming file tag |
| `adaptive.py` | calibration-based block-size selector (+ cache) |
| `protocol.py` | Server/Client simulation: approved block sizes, single-use expiring challenge, block size bound to the challenge |
| `registry.py` | local JSON registry (default) or optional Firebase registry |
| `main.py` | demo | `run_tests.py` | 29 tests (replaces test_pow, security_tests, replay_test, attack_test) |
| `benchmark.py` | sweep + adaptive evaluation, writes CSVs, plots and a markdown report |
| `proof.py`, `server.py` | thin wrappers so old imports still work (block_size now has a default) |

## What changed versus your old code
- Fixed the crash: old scripts called `generate_proof(file, seed)` but the function required `block_size`.
- The "modified file" test used a file identical to the server copy; tests now use real modified, truncated and 99%-genuine files.
- N >= 2 is enforced (tiny files shrink the block size deterministically; 1-byte files raise an error).
- Tags are computed by streaming (no whole-file read into memory).
- `serviceAccountKey.json` is NOT included. Keep your key outside any shared folder and in `.gitignore`.
  Firebase is optional and only stores the tag registry; file content is never sent there.

## Adaptive protocol
1. Client calibrates on a 16 MB prefix: every server-approved size {16..1024 KB}, randomised rounds,
   first round discarded, median per size, picks the smallest size within 5% of the fastest.
2. Client sends (user, tag, b*); the server accepts only approved sizes.
3. Server returns a fresh 256-bit seed (single use, 60 s expiry).
4. Both sides compute the unchanged PoW with the seed bound to b*, i.e. key = seed || b* (4 bytes).
   The proof is still 256 bits; communication and the security argument of Dave et al. are unchanged.

## Using the results in the paper
`results/results_report.md` contains ready-made tables and a "Key findings" list. Check every sentence against
the tables before copying it. Fill the CPU model and cache sizes from Task Manager if the report says so.
