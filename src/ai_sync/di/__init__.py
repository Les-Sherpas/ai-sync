"""Dependency-injection container package for ai-sync."""

from .bootstrap import bootstrap_runtime, create_container, reset_container
from .container import AppContainer

__all__ = ["AppContainer", "bootstrap_runtime", "create_container", "reset_container"]
