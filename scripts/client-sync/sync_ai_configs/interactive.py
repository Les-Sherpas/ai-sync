"""Interactive prompts."""

from __future__ import annotations

from dataclasses import dataclass

from .display import Display


@dataclass
class SyncOptions:
    agent_stems: frozenset[str]
    skill_names: frozenset[str]
    install_settings: bool
    use_backups: bool
    clear_first: bool


def run_interactive_prompts(
    display: Display,
    agent_stems: list[str],
    skill_names: list[str],
    *,
    clear_default: bool = False,
    backup_default: bool = False,
) -> SyncOptions | None:
    import questionary

    display.print("")
    display.panel("Space to toggle, Enter to confirm", title="Select agents to install", style="info")
    selected_agents = questionary.checkbox(
        "Agents", choices=[questionary.Choice(title=a, value=a, checked=True) for a in agent_stems]
    ).ask()
    if selected_agents is None:
        return None

    display.print("")
    display.panel("Space to toggle, Enter to confirm", title="Select skills to install", style="info")
    selected_skills = questionary.checkbox(
        "Skills", choices=[questionary.Choice(title=s, value=s, checked=True) for s in skill_names]
    ).ask()
    if selected_skills is None:
        return None

    display.print("")
    display.panel("", title="Sync options", style="info")
    install_settings = questionary.confirm("Install client settings (settings.yaml)?", default=True).ask()
    if install_settings is None:
        return None

    clear_first = questionary.confirm("Clear existing setups before syncing?", default=clear_default).ask()
    if clear_first is None:
        return None
    use_backups = False
    if clear_first:
        answer = questionary.confirm("Back up client configs before clearing?", default=backup_default).ask()
        if answer is None:
            return None
        use_backups = answer
    return SyncOptions(
        agent_stems=frozenset(selected_agents or []),
        skill_names=frozenset(selected_skills or []),
        install_settings=install_settings,
        use_backups=use_backups,
        clear_first=clear_first,
    )
