"""Backward-compatible wrappers (the old scripts import these names)."""
from pow_core import DEFAULT_BLOCK_SIZE, prove


def generate_proof(filename, seed, block_size=DEFAULT_BLOCK_SIZE):
    return prove(filename, seed, block_size)
