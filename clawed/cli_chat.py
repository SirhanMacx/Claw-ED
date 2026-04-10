"""Backward compatibility — import from clawed.transports.cli."""

from clawed.transports.cli import *  # noqa: F401, F403
from clawed.transports.cli import (  # noqa: F401, E402
    _WELCOME,
    _WELCOME_NEW,
    main,
    run_chat,
)
