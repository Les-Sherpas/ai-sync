"""Bootstrapped runtime dataclass."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_sync.di.container import AppContainer
    from ai_sync.services.apply_service import ApplyService
    from ai_sync.services.doctor_service import DoctorService
    from ai_sync.services.error_handler_service import ErrorHandlerService
    from ai_sync.services.install_service import InstallService
    from ai_sync.services.plan_service import PlanService
    from ai_sync.services.uninstall_service import UninstallService


@dataclass(frozen=True)
class RuntimeBootstrap:
    """Bootstrapped runtime dependencies for a CLI invocation."""

    container: "AppContainer"
    install_service: "InstallService"
    plan_service: "PlanService"
    apply_service: "ApplyService"
    doctor_service: "DoctorService"
    uninstall_service: "UninstallService"
    error_handler_service: "ErrorHandlerService"
