"""Protocol-neutral LiteyukiBot v7 kernel API."""

from ._version import __version__
from .action_service import ActionBackend, ActionPolicy, ActionService
from .events import (
    Action,
    ActionEnvelope,
    ActionExecutor,
    ActionGuard,
    ActionResult,
    ActorRef,
    ConversationRef,
    DispatchResult,
    EventBus,
    EventEnvelope,
    EventHandler,
    HandlerFailure,
    HandlerResult,
    Message,
    Segment,
    SendMessage,
    Subscription,
    canonical_source_event_id,
)
from .exceptions import LiteyukiError, ServiceError
from .json_value import JsonScalar, JsonValue, json_mapping, json_value
from .services import ServiceKey, ServiceRegistration, ServiceRegistry, ServiceRequirement
from .status import KERNEL_STATUS_SERVICE, KernelStatusProvider, KernelStatusSnapshot
from .tasks import ManagedTasks, TaskFailureHandler

__all__ = [
    "Action",
    "ActionBackend",
    "ActionEnvelope",
    "ActionExecutor",
    "ActionGuard",
    "ActionPolicy",
    "ActionResult",
    "ActionService",
    "ActorRef",
    "ConversationRef",
    "DispatchResult",
    "EventBus",
    "EventEnvelope",
    "EventHandler",
    "HandlerFailure",
    "HandlerResult",
    "JsonScalar",
    "JsonValue",
    "KERNEL_STATUS_SERVICE",
    "KernelStatusProvider",
    "KernelStatusSnapshot",
    "LiteyukiError",
    "ManagedTasks",
    "Message",
    "Segment",
    "SendMessage",
    "ServiceError",
    "ServiceKey",
    "ServiceRegistration",
    "ServiceRegistry",
    "ServiceRequirement",
    "Subscription",
    "TaskFailureHandler",
    "__version__",
    "canonical_source_event_id",
    "json_mapping",
    "json_value",
]
