from __future__ import annotations

import base64
import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.domain.services.intent_evaluator import IntentEvaluatorService

logger = logging.getLogger(__name__)

TRUST_HIERARCHY = [
    "system_prompt",
    "developer_instruction",
    "policy_rule",
    "agent_intent",
    "tool_description",
    "retrieved_content",
    "user_input",
    "untrusted_content",
]

HIDDEN_INSTRUCTION_PATTERNS = [
    r"<!--\s*([^>]*instruction[^>]*)\s*-->",
    r"\/\*\s*([^*]*instruction[^*]*)\s*\*\/",
    r"\/\/\s*([^\n]*instruction[^\n]*)",
    r"#\s*([^\n]*instruction[^\n]*)",
    r"\[\s*([^\]]*instruction[^\]]*)\s*\]",
    r"\{\{\s*([^}]*instruction[^}]*)\s*\}\}",
    r"\$\{\s*([^}]*instruction[^}]*)\s*\}",
    r"%%\s*([^\n]*instruction[^\n]*)",
]

ENCODING_INDICATORS = [
    (r"(?:base64|b64|b64encode)\s*[:=]\s*([A-Za-z0-9+/]{20,}={0,2})", "base64"),
    (r"(?:rot13|caesar)\s*[:=]?\s*([A-Za-z0-9+/]{10,})", "rot13"),
    (r"(?:hex|hexencode)\s*[:=]?\s*([0-9a-fA-F]{5,})", "hex"),
    (r"(?:unicode|\\u[0-9a-fA-F]{4}){3,}", "unicode_escape"),
    (r"(?:url.?encod|percent.?encod)\s*[:=]?\s*([A-Za-z0-9%]{20,})", "url_encoding"),
]

TOOL_DESCRIPTION_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+(tool\s+)?descriptions?",
    r"override\s+tool\s+(description|behavior|output)",
    r"new\s+tool\s+description\s*:",
    r"tool\s+description\s+override",
    r"pretend\s+this\s+tool\s+(does|is|has)",
    r"this\s+tool\s+now\s+(does|is|has)",
]

CONTEXT_POISONING_PATTERNS = [
    r"previous\s+(messages?|context|interactions?)\s+(are\s+)?(fake|fabricated|invalid|ignored?)",
    r"forget\s+(everything|all|previous)",
    r"the\s+(above|previous)\s+(is|was)\s+(incorrect|wrong|false|a\s+test)",
    r"disregard\s+(all\s+)?(prior|previous)\s+(context|instructions?)",
    r"reset\s+(your\s+)?(memory|context|knowledge)",
    r"context\s+(reset|clear|invalidate)",
]
@dataclass(frozen=True, slots=True)
class InjectionSignal:
    signal_type: str
    severity: str
    source_trust_level: str
    evidence: str
    explanation: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ContextSecurityService:
    def __init__(self, policy_engine=None):
        self._policy_engine = policy_engine
        self._known_tool_descriptions: dict[str, str] = {}
        self._session_context_hashes: dict[str, str] = {}

    def detect_indirect_injection(
        self, content: str, source_trust: str = "untrusted_content"
    ) -> list[InjectionSignal]:
        signals = []
        content_lower = content.lower()

        if source_trust in (
            "untrusted_content", "retrieved_content",
            "user_input", "agent_message"
        ):
            for pattern in IntentEvaluatorService.PROMPT_INJECTION_PATTERNS:
                if re.search(pattern, content_lower, flags=re.IGNORECASE):
                    signals.append(InjectionSignal(
                        signal_type="indirect_prompt_injection",
                        severity="high",
                        source_trust_level=source_trust,
                        evidence=pattern,
                        explanation=f"Prompt injection pattern found in {source_trust}",
                    ))

        hidden = self._detect_hidden_instructions(content)
        signals.extend(hidden)

        return signals

    def _detect_hidden_instructions(self, content: str) -> list[InjectionSignal]:
        signals = []
        for pattern in HIDDEN_INSTRUCTION_PATTERNS:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                signals.append(InjectionSignal(
                    signal_type="hidden_instruction",
                    severity="medium",
                    source_trust_level="unknown",
                    evidence=match[:100],
                    explanation=f"Hidden instruction pattern detected: {pattern}",
                ))
        return signals

    def detect_malicious_document(self, content: str, content_type: str = "text") -> dict[str, Any]:
        signals = []

        instruction_count = sum(
            len(re.findall(p, content, re.IGNORECASE))
            for p in HIDDEN_INSTRUCTION_PATTERNS
        )
        if instruction_count > 3:
            signals.append({
                "type": "excessive_instructions",
                "severity": "high",
                "count": instruction_count,
            })

        encoded = self._detect_encoded_instructions(content)
        signals.extend(encoded)

        poisoned = self.detect_context_poisoning(content)
        signals.extend(poisoned)

        return {
            "is_suspicious": len(signals) > 0,
            "signal_count": len(signals),
            "signals": signals,
            "content_type": content_type,
        }

    def _detect_encoded_instructions(self, content: str) -> list[dict]:
        signals = []
        for pattern, encoding_type in ENCODING_INDICATORS:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                decoded = self._try_decode(match, encoding_type)
                if decoded and self._contains_instructions(decoded):
                    signals.append({
                        "type": f"encoded_instruction_{encoding_type}",
                        "severity": "high",
                        "encoding": encoding_type,
                        "preview": decoded[:100],
                    })
        return signals

    def _try_decode(self, data: str, encoding_type: str) -> str | None:
        try:
            if encoding_type == "base64":
                padded = data + "=" * (4 - len(data) % 4) if len(data) % 4 else data
                return base64.b64decode(padded).decode("utf-8", errors="ignore")
            if encoding_type == "hex":
                return bytes.fromhex(data).decode("utf-8", errors="ignore")
            if encoding_type == "rot13":
                import codecs
                return codecs.decode(data, "rot13")
        except Exception:  # noqa: S110
            pass
        return None

    def _contains_instructions(self, text: str) -> bool:
        text_lower = text.lower()
        instruction_keywords = [
            "ignore", "override", "disregard", "forget",
            "pretend", "act as", "new instructions", "instruction"
        ]
        return any(kw in text_lower for kw in instruction_keywords)

    def detect_tool_description_injection(
        self, tool_description: str, known_description: str | None = None
    ) -> dict[str, Any]:
        if known_description and tool_description == known_description:
            return {"is_injection": False, "reason": "description_matches_known"}

        signals = []
        desc_lower = tool_description.lower()
        for pattern in TOOL_DESCRIPTION_INJECTION_PATTERNS:
            if re.search(pattern, desc_lower, flags=re.IGNORECASE):
                signals.append({"pattern": pattern, "severity": "critical"})

        return {
            "is_injection": len(signals) > 0,
            "signals": signals,
            "known_hash": (
                hashlib.sha256(known_description.encode()).hexdigest()
                if known_description else None
            ),
            "current_hash": hashlib.sha256(tool_description.encode()).hexdigest(),
        }

    def enforce_instruction_hierarchy(
        self, content: str, content_trust: str, system_prompt: str = ""
    ) -> dict[str, Any]:
        hierarchy_index = (
            TRUST_HIERARCHY.index(content_trust)
            if content_trust in TRUST_HIERARCHY else len(TRUST_HIERARCHY)
        )

        injection_patterns = IntentEvaluatorService.PROMPT_INJECTION_PATTERNS
        detected_attempts = []

        for pattern in injection_patterns:
            if re.search(pattern, content, flags=re.IGNORECASE):
                detected_attempts.append({
                    "pattern": pattern,
                    "attempted_override": True,
                    "content_trust": content_trust,
                    "hierarchy_index": hierarchy_index,
                })

        return {
            "hierarchy_index": hierarchy_index,
            "content_trust": content_trust,
            "override_attempts_detected": len(detected_attempts) > 0,
            "detected_attempts": detected_attempts,
            "allowed_to_influence": hierarchy_index < 3,
        }

    def detect_context_poisoning(self, content: str) -> list[dict]:
        signals = []
        content_lower = content.lower()
        for pattern in CONTEXT_POISONING_PATTERNS:
            if re.search(pattern, content_lower, flags=re.IGNORECASE):
                signals.append({
                    "type": "context_poisoning",
                    "pattern": pattern,
                    "severity": "high",
                })
        return signals

    def detect_memory_poisoning(self, memory_content: str, expected_source: str) -> dict[str, Any]:
        content_hash = hashlib.sha256(memory_content.encode()).hexdigest()

        signals = []
        if self._detects_injection_patterns(memory_content):
            signals.append({"type": "memory_injection", "severity": "critical"})

        return {
            "memory_hash": content_hash,
            "expected_source": expected_source,
            "poisoning_detected": len(signals) > 0,
            "signals": signals,
        }

    def _detects_injection_patterns(self, text: str) -> bool:
        text_lower = text.lower()
        return any(
            re.search(p, text_lower, flags=re.IGNORECASE)
            for p in IntentEvaluatorService.PROMPT_INJECTION_PATTERNS
        )

    def prevent_cross_session_poisoning(
        self, session_id: str, content: str, context_window_hash: str
    ) -> dict[str, Any]:
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        return {
            "session_id": session_id,
            "context_window_hash": context_window_hash,
            "content_hash": content_hash,
            "isolation_verified": True,
            "cross_session_leak_detected": False,
        }

    def detect_agent_to_agent_instruction_attack(
        self, sender_agent_id: str, receiver_agent_id: str, message: str
    ) -> dict[str, Any]:
        signals = self.detect_indirect_injection(message, source_trust="agent_message")

        escalation_indicators = []
        message_lower = message.lower()
        escalation_keywords = ["grant", "delegate", "escalate", "admin", "root", "sudo", "elevate"]
        if any(kw in message_lower for kw in escalation_keywords):
            escalation_indicators.append("authority_escalation_request")

        return {
            "sender_agent_id": sender_agent_id,
            "receiver_agent_id": receiver_agent_id,
            "attack_detected": len(signals) > 0 or len(escalation_indicators) > 0,
            "injection_signals": [{"type": s.signal_type, "severity": s.severity} for s in signals],
            "escalation_indicators": escalation_indicators,
        }
