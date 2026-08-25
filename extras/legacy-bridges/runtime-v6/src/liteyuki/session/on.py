"""Registration helpers for LiteyukiBot v6-compatible matchers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .event import MessageEvent
from .matcher import Matcher
from .rule import Rule, empty_rule


@dataclass(frozen=True, slots=True)
class MatcherDispatchResult:
    """Represent the validated matcher dispatch result contract."""
    matched: int
    handlers_called: int
    blocked: bool
    failures: tuple[str, ...] = ()


_matcher_list: list[Matcher] = []


def add_matcher(matcher: Matcher) -> Matcher:
    """Add matcher.

    Args:
        matcher: The matcher value used by the operation.

    Returns:
        The `Matcher` result produced by the operation.
    """
    for index, registered in enumerate(_matcher_list):
        if registered.priority < matcher.priority:
            _matcher_list.insert(index, matcher)
            break
    else:
        _matcher_list.append(matcher)
    return matcher


def get_matchers() -> tuple[Matcher, ...]:
    """Return matchers.

    Returns:
        The requested `tuple[Matcher, ...]` value.
    """
    return tuple(_matcher_list)


def _reset_matchers() -> None:
    """Implement the reset matchers operation for the component.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_reset_matchers`. It delegates to `clear` while keeping
        intermediate state local to the owning operation.
    """
    _matcher_list.clear()


async def _dispatch_matchers(event: MessageEvent) -> MatcherDispatchResult:
    """Dispatch matchers.

    Args:
        event: Event associated with the operation.

    Returns:
        The `MatcherDispatchResult` result produced by the operation.

    Notes:
        Internal implementation detail for `_dispatch_matchers`. It delegates to `run`, `extend` while
        keeping intermediate state local to the owning operation.
    """
    matched = 0
    handlers_called = 0
    blocked_priority: int | None = None
    failures: list[str] = []
    for matcher in tuple(_matcher_list):
        if blocked_priority is not None and matcher.priority < blocked_priority:
            break
        result = await matcher.run(event)
        if not result.matched:
            continue
        matched += 1
        handlers_called += result.handlers_called
        failures.extend(result.failures)
        if matcher.block:
            blocked_priority = matcher.priority
    return MatcherDispatchResult(
        matched=matched,
        handlers_called=handlers_called,
        blocked=blocked_priority is not None,
        failures=tuple(failures),
    )


def on_message(rule: Rule = empty_rule, priority: int = 0, block: bool = False) -> Matcher:
    """Implement the on message operation for the component.

    Args:
        rule: The rule value used by the operation.
        priority: The priority value used by the operation.
        block: The block value used by the operation.

    Returns:
        The `Matcher` result produced by the operation.
    """
    return add_matcher(Matcher(rule, priority, block))


def on_keywords(
    keywords: str | Sequence[str],
    rule: Rule = empty_rule,
    priority: int = 0,
    block: bool = False,
) -> Matcher:
    """Implement the on keywords operation for the component.

    Args:
        keywords: The keywords value used by the operation.
        rule: The rule value used by the operation.
        priority: The priority value used by the operation.
        block: The block value used by the operation.

    Returns:
        The `Matcher` result produced by the operation.
    """
    normalized = _normalize_keywords(keywords)

    @Rule
    async def keyword_rule(event: MessageEvent) -> bool:
        """Implement the keyword rule operation for the on keywords.

        Args:
            event: Event associated with the operation.

        Returns:
            Whether the requested condition is satisfied.

        Notes:
            Internal implementation detail for `on_keywords.keyword_rule`. It delegates to `any` while
            keeping intermediate state local to the owning operation.
        """
        return any(keyword in event.raw_message for keyword in normalized)

    return on_message(keyword_rule & rule, priority, block)


def on_startswith(
    keywords: str | Sequence[str],
    rule: Rule = empty_rule,
    priority: int = 0,
    block: bool = False,
) -> Matcher:
    """Implement the on startswith operation for the component.

    Args:
        keywords: The keywords value used by the operation.
        rule: The rule value used by the operation.
        priority: The priority value used by the operation.
        block: The block value used by the operation.

    Returns:
        The `Matcher` result produced by the operation.
    """
    normalized = _normalize_keywords(keywords)

    @Rule
    async def startswith_rule(event: MessageEvent) -> bool:
        """Implement the startswith rule operation for the on startswith.

        Args:
            event: Event associated with the operation.

        Returns:
            Whether the requested condition is satisfied.

        Notes:
            Internal implementation detail for `on_startswith.startswith_rule`. It delegates to `startswith`
            while keeping intermediate state local to the owning operation.
        """
        return event.raw_message.startswith(normalized)

    return on_message(startswith_rule & rule, priority, block)


def on_endswith(
    keywords: str | Sequence[str],
    rule: Rule = empty_rule,
    priority: int = 0,
    block: bool = False,
) -> Matcher:
    """Implement the on endswith operation for the component.

    Args:
        keywords: The keywords value used by the operation.
        rule: The rule value used by the operation.
        priority: The priority value used by the operation.
        block: The block value used by the operation.

    Returns:
        The `Matcher` result produced by the operation.
    """
    normalized = _normalize_keywords(keywords)

    @Rule
    async def endswith_rule(event: MessageEvent) -> bool:
        """Implement the endswith rule operation for the on endswith.

        Args:
            event: Event associated with the operation.

        Returns:
            Whether the requested condition is satisfied.

        Notes:
            Internal implementation detail for `on_endswith.endswith_rule`. It delegates to `endswith` while
            keeping intermediate state local to the owning operation.
        """
        return event.raw_message.endswith(normalized)

    return on_message(endswith_rule & rule, priority, block)


def on_fullmatch(
    keywords: str | Sequence[str],
    rule: Rule = empty_rule,
    priority: int = 0,
    block: bool = False,
) -> Matcher:
    """Implement the on fullmatch operation for the component.

    Args:
        keywords: The keywords value used by the operation.
        rule: The rule value used by the operation.
        priority: The priority value used by the operation.
        block: The block value used by the operation.

    Returns:
        The `Matcher` result produced by the operation.
    """
    normalized = _normalize_keywords(keywords)

    @Rule
    async def fullmatch_rule(event: MessageEvent) -> bool:
        """Implement the fullmatch rule operation for the on fullmatch.

        Args:
            event: Event associated with the operation.

        Returns:
            Whether the requested condition is satisfied.

        Notes:
            Internal implementation detail for `on_fullmatch.fullmatch_rule`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        return event.raw_message in normalized

    return on_message(fullmatch_rule & rule, priority, block)


def _normalize_keywords(keywords: str | Sequence[str]) -> tuple[str, ...]:
    """Normalize keywords.

    Args:
        keywords: The keywords value used by the operation.

    Returns:
        The `tuple[str, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_normalize_keywords`. It delegates to `any` while keeping
        intermediate state local to the owning operation.
    """
    normalized = (keywords,) if isinstance(keywords, str) else tuple(keywords)
    if not normalized or any(not isinstance(keyword, str) or not keyword for keyword in normalized):
        raise ValueError("matcher keywords must contain non-empty strings")
    return normalized


__all__ = [
    "MatcherDispatchResult",
    "add_matcher",
    "get_matchers",
    "on_endswith",
    "on_fullmatch",
    "on_keywords",
    "on_message",
    "on_startswith",
]
