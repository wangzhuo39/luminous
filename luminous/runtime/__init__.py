from __future__ import annotations

from luminous.runtime.application.prompts import SYSTEM_PROMPT
from luminous.runtime.application.memory_extractor import MemoryExtractionResult, MemoryExtractor
from luminous.runtime.application.notification_bridge import NotificationBridge, NotificationDelivery
from luminous.runtime.application.prompt_builder import PromptBuilder, PromptPackage
from luminous.runtime.application.proactive_engine import ProactiveDecision, ProactiveEngine
from luminous.runtime.application.runtime import CompanionRuntime
from luminous.runtime.application.state_engine import AnalyzerOutput, StateEngine, StateTransition
from luminous.runtime.application.service import CompanionService
from luminous.runtime.config import BackendConfig, PROJECT_ROOT, load_backend_config
from luminous.runtime.domain.events import ConversationEvent, ProactiveSignal
from luminous.runtime.domain.memory import MemoryHit, MemoryQuery, MemoryRecord
from luminous.runtime.domain.output import ParsedCompanionOutput, parse_model_output
from luminous.runtime.domain.presence import build_presence
from luminous.runtime.domain.state import CompanionState, RelationshipState
from luminous.runtime.infrastructure.client import (
    Message,
    ModelClient,
    ModelClientError,
    StreamTransport,
    Transport,
    openai_compatible_chat_completion,
    openai_compatible_chat_completion_stream,
)
from luminous.runtime.infrastructure.runtime_store import CompanionRuntimeStore

__all__ = [
    "BackendConfig",
    "PROJECT_ROOT",
    "load_backend_config",
    "CompanionState",
    "RelationshipState",
    "MemoryRecord",
    "MemoryHit",
    "MemoryQuery",
    "ConversationEvent",
    "ProactiveSignal",
    "Message",
    "Transport",
    "StreamTransport",
    "ModelClient",
    "ModelClientError",
    "openai_compatible_chat_completion",
    "openai_compatible_chat_completion_stream",
    "ParsedCompanionOutput",
    "parse_model_output",
    "build_presence",
    "SYSTEM_PROMPT",
    "PromptBuilder",
    "PromptPackage",
    "MemoryExtractionResult",
    "MemoryExtractor",
    "NotificationBridge",
    "NotificationDelivery",
    "AnalyzerOutput",
    "StateEngine",
    "StateTransition",
    "ProactiveDecision",
    "ProactiveEngine",
    "CompanionRuntimeStore",
    "CompanionRuntime",
    "CompanionService",
]
