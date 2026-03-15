"""Container bootstrap helpers for ai-sync."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TextIO

from dependency_injector import providers

from ai_sync.data_classes.runtime_bootstrap import RuntimeBootstrap

from .container import AppContainer


def create_container(
    *,
    environ: Mapping[str, str] | None = None,
    stdin: TextIO | None = None,
    prompt_input: Callable[[str], str] = input,
) -> AppContainer:
    """Create an application container with optional runtime overrides."""
    container = AppContainer()
    override_kwargs: dict[str, object] = {
        "prompt_input": prompt_input,
    }
    if environ is not None:
        override_kwargs["runtime_environ"] = providers.Object(environ)
    if stdin is not None:
        override_kwargs["runtime_stdin"] = providers.Object(stdin)
    container.override_providers(**override_kwargs)
    return container


def reset_container(container: AppContainer) -> None:
    """Reset provider overrides and cached singleton instances."""
    container.reset_override()
    container.reset_singletons()


def bootstrap_runtime(
    *,
    environ: Mapping[str, str] | None = None,
    stdin: TextIO | None = None,
    prompt_input: Callable[[str], str] = input,
) -> RuntimeBootstrap:
    """Create container and resolved top-level services for runtime use."""
    container = create_container(environ=environ, stdin=stdin, prompt_input=prompt_input)
    return RuntimeBootstrap(
        container=container,
        install_service=container.install_service(),
        plan_service=container.plan_service(),
        apply_service=container.apply_service(),
        doctor_service=container.doctor_service(),
        uninstall_service=container.uninstall_service(),
        error_handler_service=container.error_handler_service(),
    )
