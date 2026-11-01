"""Backward-compatible wrapper: the server runs the identical procedure on its stored copy."""
from pow_core import DEFAULT_BLOCK_SIZE, prove


def generate_server_proof(filename, seed, block_size=DEFAULT_BLOCK_SIZE):
    return prove(filename, seed, block_size)
