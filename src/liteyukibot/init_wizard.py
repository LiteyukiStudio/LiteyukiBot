"""Small full-screen setup flow used before metadata-driven custom questions."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Literal

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import AnyContainer, Dimension, HSplit, Layout
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Box, Button, Dialog, Label, RadioList, TextArea

from .config.initializer import InitializationPlan, build_initialization_plan
from .i18n import Translator, select_locale
from .resource_packs import ResourceCatalog


class WizardCancelled(RuntimeError):
    """Represent the wizard cancelled contract."""
    pass


@dataclass(frozen=True, slots=True)
class InitWizardResult:
    """Represent the validated init wizard result contract."""
    workspace: str
    locale: str
    mode: Literal["minimal", "custom"]
    warning: str | None


class _BackRequested(Exception):
    """Represent the back requested contract."""
    pass


_STYLE = Style.from_dict({"radio-selected": "fg:#00ff66 bold", "button.focused": "fg:#00ff66 bold"})


def _application(body: AnyContainer, *, back: bool) -> tuple[Application[None], dict[str, object]]:
    """Implement the application operation for the component.

    Args:
        body: The body value used by the operation.
        back: The back value used by the operation.

    Returns:
        The `tuple[Application[None], dict[str, object]]` result produced by the operation.

    Notes:
        Internal implementation detail for `_application`. It delegates to `append`, `extend`, `exit`,
        `add` while keeping intermediate state local to the owning operation.
    """
    result: dict[str, object] = {}
    bindings = KeyBindings()

    def cancel() -> None:
        """Implement the cancel operation for the application.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_application.cancel`. It delegates to `exit` while keeping
            intermediate state local to the owning operation.
        """
        result["value"] = "cancel"
        application.exit()

    def go_back() -> None:
        """Implement the go back operation for the application.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_application.go_back`. It delegates to `exit` while keeping
            intermediate state local to the owning operation.
        """
        result["value"] = "back"
        application.exit()

    buttons = []
    if back:
        buttons.append(Button("Back", handler=go_back))
    buttons.extend((Button("Cancel", handler=cancel), Button("Continue", handler=lambda: application.exit())))
    dialog = Dialog(
        title="LiteyukiBot",
        body=Box(body, padding=1),
        buttons=buttons,
        width=Dimension(preferred=76, min=36, max=110),
    )
    application: Application[None] = Application(
        Layout(dialog), key_bindings=bindings, full_screen=True, mouse_support=True, style=_STYLE
    )
    bindings.add("c-c")(lambda _event: cancel())
    bindings.add("escape")(lambda _event: go_back() if back else cancel())
    return application, result


def _choose(title: str, values: list[tuple[str, str]], *, current: str, back: bool) -> str:
    """Implement the choose operation for the component.

    Args:
        title: The title value used by the operation.
        values: The values value used by the operation.
        current: The current value used by the operation.
        back: The back value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_choose`. It delegates to `_mnemonic`, `enumerate`,
        `_application`, `_mnemonic_key` while keeping intermediate state local to the owning operation.
    """
    rendered = [(value, _mnemonic(label, index, values)) for index, (value, label) in enumerate(values)]
    choices = RadioList(values=rendered)
    choices.current_value = current
    application, result = _application(
        HSplit([Label(title), choices, Label("Use Arrow keys, Space, Enter, or green keys")]), back=back
    )
    used: set[str] = set()
    for value, label in values:
        key = _mnemonic_key(label, used)
        used.add(key)
        def select(_event: object, *, selected: str = value) -> None:
            choices.current_value = selected
            application.exit()
        bindings = application.key_bindings
        assert isinstance(bindings, KeyBindings)
        bindings.add(key)(select)
    bindings = application.key_bindings
    assert isinstance(bindings, KeyBindings)
    bindings.add("space")(lambda _event: application.exit())
    bindings.add("enter")(lambda _event: application.exit())
    application.run()
    action = result.get("value")
    if action == "cancel":
        raise WizardCancelled()
    if action == "back":
        return "back"
    return str(choices.current_value)


def _mnemonic_key(label: str, used: set[str]) -> str:
    """Implement the mnemonic key operation for the component.

    Args:
        label: The label value used by the operation.
        used: The used value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_mnemonic_key`. It delegates to `isascii`, `isalpha`,
        `lower`, `next` while keeping intermediate state local to the owning operation.
    """
    for character in label:
        if character.isascii() and character.isalpha() and character.lower() not in used:
            return character.lower()
    return next(character for character in "1234567890" if character not in used)


def _mnemonic(label: str, index: int, values: list[tuple[str, str]]) -> HTML:
    """Implement the mnemonic operation for the component.

    Args:
        label: The label value used by the operation.
        index: The index value used by the operation.
        values: The values value used by the operation.

    Returns:
        The `HTML` result produced by the operation.

    Notes:
        Internal implementation detail for `_mnemonic`. It delegates to `range`, `add`, `_mnemonic_key`,
        `next` while keeping intermediate state local to the owning operation.
    """
    used: set[str] = set()
    for previous_index in range(index):
        used.add(_mnemonic_key(values[previous_index][1], used))
    key = _mnemonic_key(label, used)
    position = next((item for item, character in enumerate(label) if character.lower() == key), -1)
    if position < 0:
        return HTML(label)
    return HTML(f"<b fg='ansigreen'>{label[:position]}<u>{label[position]}</u>{label[position + 1:]}</b>")


def _text(title: str, value: str, *, back: bool, secret: bool = False) -> str:
    """Implement the text operation for the component.

    Args:
        title: The title value used by the operation.
        value: Value to validate, transform, or store.
        back: The back value used by the operation.
        secret: The secret value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_text`. It delegates to `_application`, `run`, `get`,
        `strip` while keeping intermediate state local to the owning operation.
    """
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
    """Run init wizard.

    Args:
        workspace: The workspace value used by the operation.
        locale: The locale value used by the operation.

    Returns:
        The `InitWizardResult` result produced by the operation.
    """
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


def _logging_choices(translator: Translator) -> tuple[str, bool, bool, str, tuple[str, ...]]:
    """Implement the logging choices operation for the component.

    Args:
        translator: The translator value used by the operation.

    Returns:
        The `tuple[str, bool, bool, str, tuple[str, ...]]` result produced by the operation.

    Notes:
        Internal implementation detail for `_logging_choices`. It delegates to `_choose`, `text`,
        `_text`, `strip` while keeping intermediate state local to the owning operation.
    """
    level = _choose(
        translator.text("init.logging_level", "Logging level"),
        [(item, item) for item in ("TRACE", "DEBUG", "INFO", "WARNING", "ERROR")],
        current="INFO",
        back=True,
    )
    console = _choose(
        translator.text("init.logging_console", "Enable console logs"),
        [("yes", "Enabled"), ("no", "Disabled")],
        current="yes",
        back=True,
    ) == "yes"
    json_lines = _choose(
        translator.text("init.logging_json", "Enable JSON Lines logs"),
        [("no", "Disabled"), ("yes", "Enabled")],
        current="no",
        back=True,
    ) == "yes"
    payload_mode = _choose(
        translator.text("init.payload_mode", "Payload logging mode"),
        [("metadata", "Metadata only"), ("full", "Full redacted payloads")],
        current="metadata",
        back=True,
    )
    excluded = _text(
        translator.text("init.payload_exclude_runtimes", "Payload exclusion runtime IDs (comma-separated)"),
        "",
        back=True,
    )
    return level, console, json_lines, payload_mode, tuple(item.strip() for item in excluded.split(",") if item.strip())


def build_custom_initialization_plan(_locale: str) -> tuple[InitializationPlan, tuple[str, ...]]:
    """Collect package metadata in full-screen prompts with replay-based backtracking.

    Args:
        _locale: The locale value used by the operation.

    Returns:
        The `tuple[InitializationPlan, tuple[str, ...]]` result produced by the operation.
    """

    answers: list[str] = []
    catalog = ResourceCatalog.load(".")
    translator, _warning = Translator.from_resources(catalog, _locale)
    logging_settings = _logging_choices(translator)
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
                locale=_locale,
                logging_settings=logging_settings,
            )
        except _BackRequested:
            continue
        return plan, tuple(diagnostics)


__all__ = ["InitWizardResult", "WizardCancelled", "build_custom_initialization_plan", "run_init_wizard"]
