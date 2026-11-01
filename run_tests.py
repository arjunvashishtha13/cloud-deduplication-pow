"""
Correctness and security tests (replaces test_pow.py, security_tests.py, replay_test.py, attack_test.py).
Exit code 0 = all passed.   python run_tests.py
"""
import os
import secrets
import sys
import tempfile
import time

from adaptive import select_block_size
from pow_core import KB, MB, bind_seed, file_tag, prove, prove_parallel
from protocol import Client, Server

results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name)


def write(path, data):
    with open(path, "wb") as f:
        f.write(data)
    return path


def main():
    with tempfile.TemporaryDirectory() as d:
        P = lambda n: os.path.join(d, n)
        data = os.urandom(5 * MB + 12345)
        genuine = write(P("genuine.bin"), data)
        copy_ = write(P("copy.bin"), data)
        mid = len(data) // 2
        modified = write(P("modified.bin"), data[:mid] + bytes([data[mid] ^ 1]) + data[mid + 1:])
        unrelated = write(P("unrelated.bin"), os.urandom(len(data)))
        truncated = write(P("truncated.bin"), data[: int(len(data) * 0.99)])
        padded = write(P("partial99.bin"), data[: int(len(data) * 0.99)] + bytes(len(data) - int(len(data) * 0.99)))

        # --- core correctness
        seed = secrets.token_bytes(32)
        ref = prove(genuine, seed, 256 * KB)
        check("identical files give identical proofs", prove(copy_, seed, 256 * KB) == ref)
        check("parallel proof == sequential proof",
              all(prove_parallel(genuine, seed, kb * KB, 4) == prove(genuine, seed, kb * KB) for kb in (4, 64, 256, 1024)))
        check("'update' variant == 'concat' variant", prove(genuine, seed, 64 * KB, variant="update") == prove(genuine, seed, 64 * KB))
        check("different block sizes give different proofs", prove(genuine, seed, 64 * KB) != ref)
        for name, f in [("modified (1 byte flipped)", modified), ("unrelated", unrelated),
                        ("truncated 99%", truncated), ("99% genuine + zero padding", padded)]:
            check("proof rejected for " + name, prove(f, seed, 256 * KB) != ref)
        check("old proof does not answer a new challenge", prove(genuine, secrets.token_bytes(32), 256 * KB) != ref)

        # --- tiny files (N >= 2 rule)
        t1, t2, t3 = write(P("t1.bin"), b"x" * 32), write(P("t2.bin"), b"x" * 32), write(P("t3.bin"), b"y" * 32)
        check("tiny identical files verify", prove(t1, seed) == prove(t2, seed))
        check("tiny different files rejected", prove(t1, seed) != prove(t3, seed))
        try:
            prove(write(P("one.bin"), b"a"), seed)
            check("1-byte file raises ValueError", False)
        except ValueError:
            check("1-byte file raises ValueError", True)

        # --- protocol
        server = Server(P("srv"), approved_kb=(16, 64, 256), challenge_ttl_s=60)
        cache = P("cal.json")
        mk = lambda u: Client(u, 1, cache, candidates_kb=(16, 64, 256), sample_mb=2, rounds=2)
        r = mk("alice").upload(server, genuine)
        check("first upload is stored", r["status"] == "stored")
        tag = r["tag"]
        r = mk("bob").upload(server, copy_)
        check("owner with the full file is verified (adaptive)", r["status"] == "verified" and r["block_kb"] in (16, 64, 256))
        for name, f in [("unrelated file", unrelated), ("modified file", modified),
                        ("99% genuine file", padded), ("truncated file", truncated)]:
            r = mk("mallory").upload(server, f, claimed_tag=tag)
            check("attacker knowing only the tag is denied (%s)" % name, r["status"] == "denied")
        r = mk("bob2").upload(server, copy_, fixed_kb=64)
        check("fixed block size works", r["status"] == "verified" and r["block_kb"] == 64)

        reply = server.begin_upload("eve", tag, 5)
        check("unapproved block size rejected", reply["status"] == "rejected")

        reply = server.begin_upload("carol", tag, 64)
        resp = prove(copy_, bind_seed(reply["seed"], 64 * KB), 64 * KB)
        check("valid proof accepted once", server.verify("carol", tag, resp)["status"] == "verified")
        check("replaying the same proof is rejected (challenge is single-use)",
              server.verify("carol", tag, resp)["status"] == "denied")

        reply = server.begin_upload("dave", tag, 64)
        wrong_b = prove(copy_, bind_seed(reply["seed"], 64 * KB), 256 * KB)
        check("proof computed with a different block size is rejected", server.verify("dave", tag, wrong_b)["status"] == "denied")

        reply = server.begin_upload("erin", tag, 64)
        old = prove(copy_, bind_seed(reply["seed"], 64 * KB), 64 * KB)
        reply2 = server.begin_upload("erin", tag, 64)  # new challenge replaces the old one
        check("proof for an old challenge does not answer a new one", server.verify("erin", tag, old)["status"] == "denied")

        server.ttl = -1.0
        reply = server.begin_upload("frank", tag, 64)
        resp = prove(copy_, bind_seed(reply["seed"], 64 * KB), 64 * KB)
        check("expired challenge is rejected", server.verify("frank", tag, resp)["status"] == "denied")
        server.ttl = 60.0

        check("server rejects an upload whose tag does not match its content",
              Server(P("srv2")).store_file("x", "0" * 64, genuine)["status"] == "rejected")

        # --- adaptive selector
        info = select_block_size(genuine, (16, 64, 256), sample_mb=2, rounds=2, force=True)
        check("calibration returns an approved candidate", info["chosen_kb"] in (16, 64, 256))
        info2 = select_block_size(genuine, (16, 64, 256), sample_mb=2, rounds=2, cache_path=P("c2.json"))
        info3 = select_block_size(genuine, (16, 64, 256), sample_mb=2, rounds=2, cache_path=P("c2.json"))
        check("calibration result is cached", info3["from_cache"] and info3["chosen_kb"] == info2["chosen_kb"])
        check("calibration on a tiny file does not crash", select_block_size(t1)["chosen_kb"] > 0)

    failed = [n for n, ok in results if not ok]
    print("\n%d/%d tests passed" % (len(results) - len(failed), len(results)))
    if failed:
        print("FAILED:", failed)
        sys.exit(1)


if __name__ == "__main__":
    main()
