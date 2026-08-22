from __future__ import annotations

from dataclasses import dataclass
from os import PathLike

from ..exceptions import ConfigurationError as ConfigurationErrorBase

type LocationPart = str | int


@dataclass(frozen=True, slots=True)
class ConfigIssue:
    """A configuration problem without the potentially secret input value."""

    source: str | PathLike[str]
    message: str
    location: tuple[LocationPart, ...] = ()

    def render(self) -> str:
        """Render the config issue operation.

        Returns:
            The `str` result produced by the operation.
        """
        location = ".".join(str(part) for part in self.location)
        prefix = f"{self.source}"
        if location:
            prefix = f"{prefix}:{location}"
        return f"{prefix}: {self.message}"


class ConfigurationError(ConfigurationErrorBase):
    """Raised once with every configuration issue discovered in a load pass."""

    def __init__(self, issues: list[ConfigIssue] | tuple[ConfigIssue, ...]) -> None:
        """Initialize the configuration error.

        Args:
            issues: The issues value used by the operation.

        Returns:
            None.
        """
        if not issues:
            raise ValueError("ConfigurationError requires at least one issue")
        self.issues = tuple(issues)
        super().__init__(self._render())

    def _render(self) -> str:
        """Render the configuration error operation.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `ConfigurationError._render`. It delegates to `join`,
            `render` while keeping intermediate state local to the owning operation.
        """
        count = len(self.issues)
        heading = f"Configuration is invalid ({count} issue{'s' if count != 1 else ''}):"
        return "\n".join((heading, *(f"- {issue.render()}" for issue in self.issues)))
