"""
Core of the seed-based full-file proof of ownership (PoW) of Dave et al. (2025).

    P[i] = SHA256( B[i] || PRG(seed || i) )          PRG = HMAC-SHA256(seed, i as 8-byte big-endian)
    R[2] = SHA256( P[1] || P[2] ),  R[i] = SHA256( R[i-1] || P[i] ),  Resp = R[N]

The output of prove() is identical to the original sequential algorithm.
prove_parallel() computes the independent P[i] values in a thread pool and folds the
chain in order, so it returns exactly the same Resp (security argument unchanged).
"""
import hashlib
import hmac
import os
from collections import deque
from concurrent.futures import ThreadPoolExecutor

KB = 1024
MB = 1024 * 1024
DEFAULT_BLOCK_SIZE = 256 * KB
_TAG_CHUNK = 8 * MB


def prg(seed, i):
    return hmac.digest(seed, i.to_bytes(8, "big"), "sha256")


def effective_block_size(total_bytes, block_size):
    """The scheme needs N >= 2 blocks. For very small files the block size is reduced
    deterministically, so client and server (who hold the same file) always agree."""
    if block_size < 1:
        raise ValueError("block_size must be >= 1")
    if total_bytes < 2:
        raise ValueError("file must contain at least 2 bytes (the scheme needs N >= 2 blocks)")
    if total_bytes < 2 * block_size:
        return -(-total_bytes // 2)  # ceil(total/2)
    return block_size


def _para(block, seed, i, variant="concat"):
    if variant == "update":  # ablation: avoids the B || PRG concatenation copy
        h = hashlib.sha256()
        h.update(block)
        h.update(prg(seed, i))
        return h.digest()
    return hashlib.sha256(block + prg(seed, i)).digest()


class _Chain:
    def __init__(self):
        self.first = None
        self.r = None

    def add(self, i, p):
        if i == 1:
            self.first = p
        elif i == 2:
            self.r = hashlib.sha256(self.first + p).digest()
        else:
            self.r = hashlib.sha256(self.r + p).digest()

    def result(self):
        if self.r is None:
            raise ValueError("fewer than 2 blocks were read (file changed while reading?)")
        return self.r


def _total_bytes(path, max_bytes):
    total = os.path.getsize(path)
    return min(total, max_bytes) if max_bytes else total


def _blocks(f, total, b):
    remaining = total
    while remaining > 0:
        block = f.read(min(b, remaining))
        if not block:
            break
        remaining -= len(block)
        yield block


def prove(path, seed, block_size=DEFAULT_BLOCK_SIZE, max_bytes=None, variant="concat"):
    """Sequential proof generation / verification (client and server run the same code)."""
    total = _total_bytes(path, max_bytes)
    b = effective_block_size(total, block_size)
    chain = _Chain()
    with open(path, "rb") as f:
        for i, block in enumerate(_blocks(f, total, b), 1):
            chain.add(i, _para(block, seed, i, variant))
    return chain.result()


def prove_parallel(path, seed, block_size=DEFAULT_BLOCK_SIZE, threads=4, max_bytes=None, variant="concat"):
    total = _total_bytes(path, max_bytes)
    b = effective_block_size(total, block_size)
    chain = _Chain()
    window = max(2, threads * 4)  # bounds memory: at most `window` blocks in flight
    pending = deque()
    with ThreadPoolExecutor(max_workers=threads) as ex, open(path, "rb") as f:
        for i, block in enumerate(_blocks(f, total, b), 1):
            pending.append((i, ex.submit(_para, block, seed, i, variant)))
            if len(pending) >= window:
                j, fut = pending.popleft()
                chain.add(j, fut.result())
        while pending:
            j, fut = pending.popleft()
            chain.add(j, fut.result())
    return chain.result()


def prove_with(path, seed, block_size=DEFAULT_BLOCK_SIZE, threads=1, max_bytes=None, variant="concat"):
    if threads and threads > 1:
        return prove_parallel(path, seed, block_size, threads, max_bytes, variant)
    return prove(path, seed, block_size, max_bytes, variant)


def bind_seed(seed, block_size):
    """Binds the chosen block size to the challenge so it cannot be swapped mid-protocol."""
    return seed + int(block_size).to_bytes(4, "big")


def file_tag(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(_TAG_CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
