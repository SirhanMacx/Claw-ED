"""Backward-compatibility shim -- the real package is now ``clawed`` (Claw-ED).

All imports like ``from eduagent.X import Y`` are transparently
redirected to ``from clawed.X import Y`` via the import hook in _compat.
"""

from eduagent._compat import install as _install_compat

_install_compat()

from clawed import *  # noqa: F401, F403, E402
from clawed import __author__ as __author__  # noqa: E402
from clawed import __description__ as __description__  # noqa: E402
from clawed import __version__ as __version__  # noqa: E402
