"""Which pick engine to run: "engine1" (engine.py, the live bots) or "engine2" (engine2.py, in testing).

Both take a BotContext and return the same shapes, so the Lab, Bot Brain and the bot report can run either.
"""
from __future__ import annotations

from types import ModuleType

DEFAULT = "engine1"
NAMES = ("engine1", "engine2")


def get(name: str = "") -> ModuleType:
    if name == "engine2":
        from . import engine2
        return engine2
    from . import engine
    return engine
