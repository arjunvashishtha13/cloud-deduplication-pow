"""
Demo of secure deduplication with proof of ownership and adaptive block size.

    python main.py                      # fully local demo, no network, no keys needed
    python main.py --file myfile.bin    # use your own file (>= 2 bytes)
    python main.py --fixed-kb 256       # skip calibration, use a fixed block size
    python main.py --firebase-key KEY.json --firebase-url URL   # optional Firebase tag registry
"""
import argparse
import os
import shutil

from pow_core import MB
from protocol import Client, Server
from registry import FirebaseRegistry, LocalRegistry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None)
    ap.add_argument("--workdir", default="demo_run")
    ap.add_argument("--fixed-kb", type=int, default=None)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--firebase-key", default=None)
    ap.add_argument("--firebase-url", default=None)
    a = ap.parse_args()

    os.makedirs(a.workdir, exist_ok=True)
    storage = os.path.join(a.workdir, "server_storage")
    shutil.rmtree(storage, ignore_errors=True)

    if a.file is None:
        a.file = os.path.join(a.workdir, "sample.bin")
        with open(a.file, "wb") as f:
            f.write(os.urandom(16 * MB))
    other = os.path.join(a.workdir, "attacker_file.bin")
    with open(other, "wb") as f:
        f.write(os.urandom(max(os.path.getsize(a.file), 2)))

    if a.firebase_key and a.firebase_url:
        registry = FirebaseRegistry(a.firebase_key, a.firebase_url)
        print("Using Firebase registry (root: pow_demo, reset at start).")
    else:
        registry = LocalRegistry(os.path.join(a.workdir, "registry.json"))
        if os.path.exists(registry.path):
            os.remove(registry.path)
        registry = LocalRegistry(registry.path)

    server = Server(storage, registry, threads=a.threads)
    cache = os.path.join(a.workdir, "calibration_cache.json")
    if os.path.exists(cache):
        os.remove(cache)  # fresh demo: calibrate on the first upload, reuse for later ones

    print("=" * 40 + "\n  SECURE CLOUD DEDUPLICATION (PoW)\n" + "=" * 40)

    r1 = Client("alice", a.threads, cache).upload(server, a.file, a.fixed_kb)
    print("\n[alice] first upload ->", r1["status"], "| tag", r1["tag"][:16] + "...")

    r2 = Client("bob", a.threads, cache).upload(server, a.file, a.fixed_kb)
    print("[bob]   same file     ->", r2["status"].upper(),
          "| block %s KB | calibration %.2fs | proof %.3fs | verify %.3fs" % (
              r2.get("block_kb"), r2.get("calibration_s", 0), r2.get("proof_s", 0), r2.get("verification_s", 0)))

    r3 = Client("mallory", a.threads, cache).upload(server, other, a.fixed_kb, claimed_tag=r1["tag"])
    print("[mallory] knows tag only ->", r3["status"].upper(), "|", r3.get("reason", ""))

    print("\nOwners:", registry.owners(r1["tag"]))


if __name__ == "__main__":
    main()
