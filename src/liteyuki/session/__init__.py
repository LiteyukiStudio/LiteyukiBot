"""Supported LiteyukiBot v6 session compatibility API."""

from .event import MessageEvent, ReplyPayload
from .matcher import EventHandler, Matcher, MatcherRunResult
from .models import Member, Role, Scene, SceneType, Session, User
from .on import (
    MatcherDispatchResult,
    add_matcher,
    get_matchers,
    on_endswith,
    on_fullmatch,
    on_keywords,
    on_message,
    on_startswith,
)
from .rule import Rule, RuleHandlerFunc, empty_rule, is_su_rule

__all__ = [
    "EventHandler",
    "Matcher",
    "MatcherDispatchResult",
    "MatcherRunResult",
    "Member",
    "MessageEvent",
    "ReplyPayload",
    "Role",
    "Rule",
    "RuleHandlerFunc",
    "Scene",
    "SceneType",
    "Session",
    "User",
    "add_matcher",
    "empty_rule",
    "get_matchers",
    "is_su_rule",
    "on_endswith",
    "on_fullmatch",
    "on_keywords",
    "on_message",
    "on_startswith",
]
