"""Versioned random inputs shared by the lattice and graph automata.

Split version 1 uses PCG64 with SeedSequence-derived, fixed stream IDs.
Initialization and perturbation have persistent generators. Fault uniforms and
standardized telemetry noise are regenerated for the absolute, zero-based step
and full population, then reshaped in row-major order. Thus node i on a graph
has the same potential inputs as flat cell i on a lattice of equal size.
These are potential inputs: only eligible cells experience their effects.
"""
from collections.abc import Mapping
import operator
import numpy as np


VERSION = 1
STREAM_IDS = {'initialization': 0, 'perturbation': 1, 'faults': 2, 'telemetry': 3}


def _nonnegative_integer(value, name):
    if isinstance(value, (bool, np.bool_)):
        raise ValueError(f'{name} must be a nonnegative integer')
    try:
        value = operator.index(value)
    except TypeError as exc:
        raise ValueError(f'{name} must be a nonnegative integer') from exc
    if value < 0:
        raise ValueError(f'{name} must be a nonnegative integer')
    return value


class RandomProtocol:
    """Seed bookkeeping; legacy draws remain on the automaton's public rng."""

    def __init__(self, seed=None, randomness='legacy', stream_seeds=None):
        if randomness not in ('legacy', 'split'):
            raise ValueError(f'unknown randomness: {randomness}')
        if randomness == 'legacy' and stream_seeds is not None:
            raise ValueError('stream_seeds requires randomness="split"')
        if stream_seeds is not None and not isinstance(stream_seeds, Mapping):
            raise ValueError('stream_seeds must be a mapping')
        overrides = {} if stream_seeds is None else dict(stream_seeds)
        if any(name not in STREAM_IDS for name in overrides):
            raise ValueError('unknown random stream name')
        overrides = {name: _nonnegative_integer(value, name)
                     for name, value in overrides.items()}
        self.randomness = randomness
        self.seed = (int(np.random.SeedSequence().entropy) if seed is None
                     else _nonnegative_integer(seed, 'seed'))
        self.stream_seeds = {}
        if randomness == 'split':
            for name, stream_id in STREAM_IDS.items():
                words = np.random.SeedSequence(
                    self.seed, spawn_key=(VERSION, stream_id)).generate_state(4)
                derived = sum(int(word) << (32 * i) for i, word in enumerate(words))
                self.stream_seeds[name] = overrides.get(name, derived)
            self.initialization = self._generator('initialization')
            self.perturbation = self._generator('perturbation')

    def _generator(self, name, step=None):
        key = () if step is None else (VERSION, step)
        sequence = np.random.SeedSequence(self.stream_seeds[name], spawn_key=key)
        return np.random.Generator(np.random.PCG64(sequence))

    def field(self, name, step, shape):
        """Regenerate one potential field without consuming persistent RNGs."""
        if self.randomness != 'split':
            raise ValueError('random input preview requires randomness="split"')
        step = _nonnegative_integer(step, 'step')
        rng = self._generator(name, step)
        size = int(np.prod(shape))
        values = (rng.random(size) if name == 'faults'
                  else rng.standard_normal(size))
        return values.reshape(shape)

    def inputs(self, step, shape):
        return {'fault_uniform': self.field('faults', step, shape),
                'telemetry_standard_normal': self.field('telemetry', step, shape)}

    def info(self):
        return {'randomness': self.randomness,
                'version': VERSION if self.randomness == 'split' else 0,
                'seed': self.seed, 'stream_seeds': self.stream_seeds.copy()}
