"""Output backends: each turns a Program into source text for one machine."""
from __future__ import annotations

from typing import Callable

from ..program import Program
from ..settings import Settings

BACKENDS: dict[str, Callable[[Program, Settings], str]] = {}

from .cnc90 import emit as _emit_cnc90  # noqa: E402  (after BACKENDS exists)

BACKENDS['cnc90'] = _emit_cnc90
