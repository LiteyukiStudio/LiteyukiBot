"""Registration helpers for LiteyukiBot v6-compatible matchers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .event import MessageEvent
from .matcher import Matcher
from .rule import Rule, empty_rule


@dataclass(frozen=True, slots=True)
class MatcherDispatchResult:
    matched: int
    handlers_called: int
    blocked: bool
    failures: tuple[str, ...] = ()


_matcher_list: list[Matcher] = []


def add_matcher(matcher: Matcher) -> Matcher:
    for index, registered in enumerate(_matcher_list):
        if registered.priority < matcher.priority:
            _matcher_list.insert(index, matcher)
            break
    else:
        _matcher_list.append(matcher)
    return matcher


def get_matchers() -> tuple[Matcher, ...]:
    return tuple(_matcher_list)


def _reset_matchers() -> None:
    _matcher_list.clear()


async def _dispatch_matchers(event: MessageEvent) -> MatcherDispatchResult:
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
    return add_matcher(Matcher(rule, priority, block))


def on_keywords(
    keywords: str | Sequence[str],
    rule: Rule = empty_rule,
    priority: int = 0,
    block: bool = False,
) -> Matcher:
    normalized = _normalize_keywords(keywords)

    @Rule
    async def keyword_rule(event: MessageEvent) -> bool:
        return any(keyword in event.raw_message for keyword in normalized)

    return on_message(keyword_rule & rule, priority, block)


def on_startswith(
    keywords: str | Sequence[str],
    rule: Rule = empty_rule,
    priority: int = 0,
    block: bool = False,
) -> Matcher:
    normalized = _normalize_keywords(keywords)

    @Rule
    async def startswith_rule(event: MessageEvent) -> bool:
        return event.raw_message.startswith(normalized)

    return on_message(startswith_rule & rule, priority, block)


def on_endswith(
    keywords: str | Sequence[str],
    rule: Rule = empty_rule,
    priority: int = 0,
    block: bool = False,
) -> Matcher:
    normalized = _normalize_keywords(keywords)

    @Rule
    async def endswith_rule(event: MessageEvent) -> bool:
        return event.raw_message.endswith(normalized)

    return on_message(endswith_rule & rule, priority, block)


def on_fullmatch(
    keywords: str | Sequence[str],
    rule: Rule = empty_rule,
    priority: int = 0,
    block: bool = False,
) -> Matcher:
    normalized = _normalize_keywords(keywords)

    @Rule
    async def fullmatch_rule(event: MessageEvent) -> bool:
        return event.raw_message in normalized

    return on_message(fullmatch_rule & rule, priority, block)


def _normalize_keywords(keywords: str | Sequence[str]) -> tuple[str, ...]:
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
