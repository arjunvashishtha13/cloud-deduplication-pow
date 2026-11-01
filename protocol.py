"""
In-process simulation of the PoW protocol with adaptive block size.

  1. client: tag = SHA256(file); picks block size b* by calibration (or a fixed one)
  2. client -> server: (user, tag, b*)        server checks b* is in its approved set
  3. server -> client: fresh 256-bit seed     (one-time, expires)
  4. client: Resp = PoW(file, bind(seed, b*), b*)       bind() ties b* to the challenge
  5. server recomputes on its stored copy with the same b*, constant-time compare
"""
import hmac
import os
import secrets
import shutil
import time

from adaptive import APPROVED_KB, DEFAULT_ROUNDS, DEFAULT_SAMPLE_MB, DEFAULT_TOL, select_block_size
from pow_core import KB, bind_seed, file_tag, prove_with
from registry import LocalRegistry


class Server:
    def __init__(self, storage_dir, registry=None, approved_kb=APPROVED_KB, challenge_ttl_s=60.0, threads=1):
        self.storage_dir = storage_dir
        os.makedirs(storage_dir, exist_ok=True)
        self.registry = registry or LocalRegistry(os.path.join(storage_dir, "registry.json"))
        self.approved_kb = tuple(approved_kb)
        self.ttl = challenge_ttl_s
        self.threads = threads
        self._challenges = {}

    def _path(self, tag):
        return os.path.join(self.storage_dir, tag + ".bin")

    def begin_upload(self, user, tag, block_kb):
        if not self.registry.exists(tag):
            return {"status": "upload_required"}
        if block_kb not in self.approved_kb:
            return {"status": "rejected", "reason": "block size not approved"}
        seed = secrets.token_bytes(32)
        self._challenges[(user, tag)] = (seed, block_kb, time.monotonic() + self.ttl)
        return {"status": "challenge", "seed": seed, "block_kb": block_kb}

    def store_file(self, user, tag, path):
        if file_tag(path) != tag:
            return {"status": "rejected", "reason": "tag does not match the uploaded file"}
        shutil.copyfile(path, self._path(tag))
        self.registry.add(tag, user, os.path.basename(path))
        return {"status": "stored"}

    def verify(self, user, tag, response):
        entry = self._challenges.pop((user, tag), None)  # single use: replays are rejected
        if entry is None:
            return {"status": "denied", "reason": "no active challenge"}
        seed, kb, expiry = entry
        if time.monotonic() > expiry:
            return {"status": "denied", "reason": "challenge expired"}
        if not os.path.exists(self._path(tag)):
            return {"status": "denied", "reason": "stored copy not found"}
        t0 = time.perf_counter()
        expected = prove_with(self._path(tag), bind_seed(seed, kb * KB), kb * KB, self.threads)
        verification_s = time.perf_counter() - t0
        if isinstance(response, bytes) and hmac.compare_digest(expected, response):
            self.registry.add(tag, user, "")
            return {"status": "verified", "verification_s": verification_s}
        return {"status": "denied", "reason": "proof mismatch", "verification_s": verification_s}


class Client:
    def __init__(self, user, threads=1, cache_path=None, candidates_kb=APPROVED_KB,
                 sample_mb=DEFAULT_SAMPLE_MB, rounds=DEFAULT_ROUNDS, tol=DEFAULT_TOL):
        self.user = user
        self.threads = threads
        self.cache_path = cache_path
        self.candidates_kb = candidates_kb
        self.sample_mb = sample_mb
        self.rounds = rounds
        self.tol = tol

    def upload(self, server, path, fixed_kb=None, claimed_tag=None):
        """claimed_tag lets an attacker who only knows a tag (not the file) try to claim ownership."""
        tag = claimed_tag or file_tag(path)
        calibration_s, kb, scores = 0.0, fixed_kb, None
        if kb is None:
            info = select_block_size(path, self.candidates_kb, self.threads, self.sample_mb,
                                     self.rounds, self.tol, self.cache_path)
            kb, calibration_s, scores = info["chosen_kb"], info["calibration_s"], info.get("scores")
        reply = server.begin_upload(self.user, tag, kb)
        if reply["status"] == "upload_required":
            out = server.store_file(self.user, tag, path)
            out.update(tag=tag)
            return out
        if reply["status"] != "challenge":
            reply.update(tag=tag)
            return reply
        kb = reply["block_kb"]
        t0 = time.perf_counter()
        try:
            resp = prove_with(path, bind_seed(reply["seed"], kb * KB), kb * KB, self.threads)
        except ValueError as e:  # e.g. file too small to form 2 blocks
            return {"status": "denied", "reason": str(e), "tag": tag}
        proof_s = time.perf_counter() - t0
        out = server.verify(self.user, tag, resp)
        out.update(tag=tag, block_kb=kb, calibration_s=calibration_s, proof_s=proof_s, scores=scores)
        return out
