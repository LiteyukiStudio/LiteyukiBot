"""Small full-screen setup flow used before metadata-driven custom questions."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Literal

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import AnyContainer, HSplit, Layout
from prompt_toolkit.widgets import Box, Button, Dialog, Label, RadioList, TextArea

from .config.initializer import InitializationPlan, build_initialization_plan
from .i18n import Translator, select_locale
from .resource_packs import ResourceCatalog


class WizardCancelled(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class InitWizardResult:
    workspace: str
    locale: str
    mode: Literal["minimal", "custom"]
    warning: str | None


class _BackRequested(Exception):
    pass


def _application(body: AnyContainer, *, back: bool) -> tuple[Application[None], dict[str, object]]:
    result: dict[str, object] = {}
    bindings = KeyBindings()

    def cancel() -> None:
        result["value"] = "cancel"
        application.exit()

    def go_back() -> None:
        result["value"] = "back"
        application.exit()

    buttons = []
    if back:
        buttons.append(Button("Back", handler=go_back))
    buttons.extend((Button("Cancel", handler=cancel), Button("Continue", handler=lambda: application.exit())))
    dialog = Dialog(title="LiteyukiBot", body=Box(body, padding=1), buttons=buttons, width=76)
    application: Application[None] = Application(
        Layout(dialog), key_bindings=bindings, full_screen=True, mouse_support=True
    )
    bindings.add("c-c")(lambda _event: cancel())
    bindings.add("escape")(lambda _event: go_back() if back else cancel())
    return application, result


def _choose(title: str, values: list[tuple[str, str]], *, current: str, back: bool) -> str:
    choices = RadioList(values=values)
    choices.current_value = current
    application, result = _application(HSplit([Label(title), choices]), back=back)
    application.run()
    action = result.get("value")
    if action == "cancel":
        raise WizardCancelled()
    if action == "back":
        return "back"
    return str(choices.current_value)


def _text(title: str, value: str, *, back: bool, secret: bool = False) -> str:
    field = TextArea(text=value, multiline=False, password=secret)
    application, result = _application(HSplit([Label(title), field]), back=back)
    application.run()
    action = result.get("value")
    if action == "cancel":
        raise WizardCancelled()
    if action == "back":
        return "back"
    return field.text.strip() or value


def run_init_wizard(workspace: str, locale: str = "auto") -> InitWizardResult:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError("Interactive setup requires a terminal. Use --non-interactive instead.")
    catalog = ResourceCatalog.load(".")
    translator, _ = Translator.from_resources(catalog, locale)
    selected_locale = locale
    selected_workspace = workspace
    mode: Literal["minimal", "custom"] = "minimal"
    step = 0
    while True:
        if step == 0:
            choice = _choose(
                translator.text("wizard.language", "Language"),
                [("auto", "Automatic"), ("zh-CN", "简体中文"), ("en-US", "English")],
                current=selected_locale,
                back=False,
            )
            selected_locale = choice
            translator, warning = Translator.from_resources(catalog, selected_locale)
            step = 1
        elif step == 1:
            choice = _text(translator.text("wizard.workspace", "Workspace"), selected_workspace, back=True)
            if choice == "back":
                step = 0
            else:
                selected_workspace = choice
                step = 2
        elif step == 2:
            choice = _choose(
                translator.text("wizard.mode", "Setup mode"),
                [
                    ("minimal", translator.text("wizard.mode.minimal", "Minimal configuration")),
                    ("custom", translator.text("wizard.mode.custom", "Custom configuration")),
                ],
                current=mode,
                back=True,
            )
            if choice == "back":
                step = 1
            else:
                mode = choice  # type: ignore[assignment]
                step = 3
        else:
            choice = _choose(
                "\n".join(
                    (
                        translator.text("wizard.review", "Review"),
                        f"{translator.text('wizard.workspace', 'Workspace')}: {selected_workspace}",
                        f"{translator.text('wizard.language', 'Language')}: {selected_locale}",
                        f"{translator.text('wizard.mode', 'Setup mode')}: {mode}",
                    )
                ),
                [("create", translator.text("wizard.create", "Create configuration"))],
                current="create",
                back=True,
            )
            if choice == "back":
                step = 2
            else:
                _selected, warning = select_locale(selected_locale)
                return InitWizardResult(selected_workspace, selected_locale, mode, warning)


def build_custom_initialization_plan(_locale: str) -> tuple[InitializationPlan, tuple[str, ...]]:
    """Collect package metadata in full-screen prompts with replay-based backtracking."""

    answers: list[str] = []
    while True:
        cursor = 0
        diagnostics: list[str] = []

        def ask(label: str, default: str, *, secret: bool = False) -> str:
            nonlocal cursor
            if cursor < len(answers):
                value = answers[cursor]
                cursor += 1
                return value
            while True:
                value = _text(label, default, back=cursor > 0, secret=secret)
                if value == "back":
                    if cursor:
                        answers.pop()
                    raise _BackRequested()
                if not secret or value:
                    break
            answers.append(value)
            cursor += 1
            return value

        try:
            plan = build_initialization_plan(
                prompt=lambda label, default: ask(label, default),
                secret_prompt=lambda label: ask(label, "", secret=True),
                output=diagnostics.append,
            )
        except _BackRequested:
            continue
        return plan, tuple(diagnostics)


__all__ = ["InitWizardResult", "WizardCancelled", "build_custom_initialization_plan", "run_init_wizard"]
