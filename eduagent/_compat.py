"""Import hook that redirects eduagent.* imports to clawed.* modules.

This allows all existing code that does ``from eduagent.X import Y``
to transparently work after the package rename to Claw-ED (clawed).
"""

from __future__ import annotations

import importlib
import sys
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import ModuleSpec


class _EduagentRedirectFinder(MetaPathFinder):
    """Intercepts ``import eduagent.X`` and redirects to ``import clawed.X``."""

    _PREFIX = "eduagent."

    def find_spec(self, fullname, path, target=None):
        if fullname == "eduagent":
            return None  # Let the real eduagent/__init__.py load normally
        if fullname.startswith(self._PREFIX):
            clawed_name = "clawed" + fullname[len("eduagent") :]
            return ModuleSpec(fullname, _EduagentRedirectLoader(clawed_name))
        return None


class _EduagentRedirectLoader(Loader):
    """Loads the clawed.* module and registers it under the eduagent.* name.

    Instead of creating a wrapper module, we directly alias the real clawed
    module. This ensures that patching ``clawed.X.func`` is visible when
    accessed via ``eduagent.X.func`` and vice versa.
    """

    def __init__(self, clawed_name: str):
        self._clawed_name = clawed_name

    def create_module(self, spec):
        # Import the real clawed module and return it directly.
        # This way, sys.modules["eduagent.X"] IS sys.modules["clawed.X"].
        return importlib.import_module(self._clawed_name)

    def exec_module(self, module):
        # Module was already fully loaded in create_module — nothing to do.
        # Register the alias so both names resolve to the same object.
        sys.modules[module.__name__] = module


def install():
    """Install the import redirect hook. Idempotent."""
    for finder in sys.meta_path:
        if isinstance(finder, _EduagentRedirectFinder):
            return
    sys.meta_path.insert(0, _EduagentRedirectFinder())
