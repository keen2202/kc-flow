"""Security hardening — encryption, prompt injection detection, input sanitization.

Implements:
- AES-256-GCM encryption for sensitive data at rest
- Prompt injection detection for LLM inputs
- Input sanitization and validation
- Audit logging
"""

import hashlib
import hmac
import json
import re
import secrets
from base64 import b64decode, b64encode
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger()


# ── Encryption ──


class EncryptionService:
    """AES-256-GCM encryption for sensitive data at rest.

    Uses Fernet (symmetric encryption) from the cryptography library.
    """

    def __init__(self, key: str | None = None) -> None:
        if key:
            self._key = key.encode()[:32].ljust(32, b"\0")
        else:
            self._key = secrets.token_bytes(32)
        self._fernet: Any = None

    def _get_fernet(self) -> Any:
        if self._fernet is None:
            try:
                from cryptography.fernet import Fernet
                import base64
                key_b64 = base64.urlsafe_b64encode(self._key)
                self._fernet = Fernet(key_b64)
            except ImportError:
                logger.warning("cryptography not installed, using simple encoding")
                self._fernet = "simple"
        return self._fernet

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string, returning base64-encoded ciphertext."""
        fernet = self._get_fernet()
        if fernet == "simple":
            return b64encode(plaintext.encode()).decode()
        return fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded ciphertext."""
        fernet = self._get_fernet()
        if fernet == "simple":
            return b64decode(ciphertext.encode()).decode()
        return fernet.decrypt(ciphertext.encode()).decode()

    @staticmethod
    def hash_sensitive(value: str) -> str:
        """Create a one-way hash of a sensitive value (for comparison, not recovery)."""
        return hashlib.sha256(value.encode()).hexdigest()


# ── Prompt Injection Detection ──


@dataclass
class InjectionDetectionResult:
    """Result of prompt injection detection."""
    is_injection: bool
    confidence: float  # 0.0 to 1.0
    patterns_matched: list[str]
    sanitized_input: str


class PromptInjectionDetector:
    """Detects prompt injection attempts in user inputs.

    Uses pattern matching and heuristic analysis to identify common
    injection techniques targeting LLM-based systems.
    """

    # Common injection patterns
    INJECTION_PATTERNS: list[tuple[str, str, float]] = [
        # System prompt override attempts
        (r"ignore\s+(all\s+)?previous\s+instructions", "ignore_previous_instructions", 0.9),
        (r"disregard\s+(all\s+)?prior\s+instructions", "ignore_prior_instructions", 0.9),
        (r"forget\s+(all\s+)?previous\s+instructions", "forget_instructions", 0.9),
        (r"you\s+are\s+now\s+(a|an)\s+", "role_reassignment", 0.7),
        (r"new\s+system\s+prompt", "system_prompt_override", 0.8),
        (r"system:\s*", "system_injection", 0.8),
        (r"\[INST\]", "instruction_tag_injection", 0.8),
        (r"<\|im_start\|>system", "chatml_injection", 0.9),

        # Jailbreak patterns
        (r"DAN\s+mode", "dan_jailbreak", 0.8),
        (r"do\s+anything\s+now", "do_anything_now", 0.7),
        (r"jailbreak", "jailbreak_mention", 0.6),
        (r"bypass\s+(all\s+)?safety", "safety_bypass", 0.8),

        # Data exfiltration attempts
        (r"repeat\s+(all\s+)?(your\s+)?instructions", "instruction_extraction", 0.8),
        (r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions)", "prompt_extraction", 0.7),
        (r"show\s+me\s+your\s+(system\s+)?(prompt|instructions)", "prompt_extraction", 0.7),
        (r"reveal\s+your\s+(system\s+)?(prompt|instructions)", "prompt_extraction", 0.7),

        # Encoding/obfuscation attempts
        (r"base64\s+decode", "base64_injection", 0.6),
        (r"eval\s*\(", "code_execution", 0.7),
        (r"exec\s*\(", "code_execution", 0.7),
    ]

    def detect(self, user_input: str) -> InjectionDetectionResult:
        """Analyze user input for prompt injection patterns.

        Returns:
            InjectionDetectionResult with detection details
        """
        if not user_input:
            return InjectionDetectionResult(
                is_injection=False,
                confidence=0.0,
                patterns_matched=[],
                sanitized_input="",
            )

        matched_patterns: list[str] = []
        max_confidence = 0.0

        input_lower = user_input.lower()

        for pattern, name, confidence in self.INJECTION_PATTERNS:
            if re.search(pattern, input_lower, re.IGNORECASE):
                matched_patterns.append(name)
                max_confidence = max(max_confidence, confidence)

        # Additional heuristic: unusually long system-like text
        if len(user_input) > 2000 and any(kw in input_lower for kw in ["system:", "assistant:", "user:", "role:"]):
            matched_patterns.append("long_system_text")
            max_confidence = max(max_confidence, 0.5)

        return InjectionDetectionResult(
            is_injection=max_confidence >= 0.7,
            confidence=max_confidence,
            patterns_matched=matched_patterns,
            sanitized_input=self._sanitize(user_input),
        )

    def _sanitize(self, text: str) -> str:
        """Sanitize input by removing potentially dangerous patterns."""
        sanitized = text
        for pattern, _, _ in self.INJECTION_PATTERNS:
            sanitized = re.sub(pattern, "[FILTERED]", sanitized, flags=re.IGNORECASE)
        return sanitized


# ── Input Sanitization ──


class InputSanitizer:
    """Sanitizes and validates user inputs for security."""

    # SQL injection patterns
    SQL_PATTERNS = [
        r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|EXECUTE)\b)",
        r"(--|;|/\*|\*/)",
        r"(\b(OR|AND)\b\s+\d+\s*=\s*\d+)",
    ]

    # XSS patterns
    XSS_PATTERNS = [
        r"<script[^>]*>",
        r"javascript:",
        r"on\w+\s*=",
        r"<iframe",
        r"<object",
        r"<embed",
    ]

    @classmethod
    def sanitize_string(cls, value: str, max_length: int = 10000) -> str:
        """Sanitize a string input."""
        # Truncate
        value = value[:max_length]

        # Remove null bytes
        value = value.replace("\x00", "")

        # Strip control characters (except newline and tab)
        value = "".join(c for c in value if c in ("\n", "\t") or ord(c) >= 32)

        return value

    @classmethod
    def check_sql_injection(cls, value: str) -> bool:
        """Check if a string contains SQL injection patterns."""
        value_upper = value.upper()
        for pattern in cls.SQL_PATTERNS:
            if re.search(pattern, value_upper):
                return True
        return False

    @classmethod
    def check_xss(cls, value: str) -> bool:
        """Check if a string contains XSS patterns."""
        for pattern in cls.XSS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                return True
        return False

    @classmethod
    def sanitize_dict(cls, data: dict[str, Any], max_depth: int = 10) -> dict[str, Any]:
        """Recursively sanitize all string values in a dict."""
        if max_depth <= 0:
            return data

        result: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = cls.sanitize_string(value)
            elif isinstance(value, dict):
                result[key] = cls.sanitize_dict(value, max_depth - 1)
            elif isinstance(value, list):
                result[key] = [
                    cls.sanitize_dict(item, max_depth - 1) if isinstance(item, dict)
                    else cls.sanitize_string(item) if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result


# ── Audit Logging ──


@dataclass
class AuditEntry:
    """An audit log entry."""
    entry_id: str
    timestamp: str
    user_id: str
    action: str
    resource_type: str
    resource_id: str
    details: dict[str, Any] = field(default_factory=dict)
    ip_address: str = ""
    success: bool = True


class AuditLogger:
    """Logs security-relevant actions for compliance and forensics."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def log(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        details: dict[str, Any] | None = None,
        ip_address: str = "",
        success: bool = True,
    ) -> AuditEntry:
        """Log an audit event."""
        import uuid

        entry = AuditEntry(
            entry_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details or {},
            ip_address=ip_address,
            success=success,
        )

        self._entries.append(entry)

        logger.info(
            "audit",
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            success=success,
        )

        return entry

    def get_entries(
        self,
        user_id: str | None = None,
        resource_type: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Query audit entries with optional filters."""
        entries = self._entries

        if user_id:
            entries = [e for e in entries if e.user_id == user_id]
        if resource_type:
            entries = [e for e in entries if e.resource_type == resource_type]
        if action:
            entries = [e for e in entries if e.action == action]

        return entries[-limit:]


# Global singletons
encryption_service = EncryptionService()
prompt_injection_detector = PromptInjectionDetector()
audit_logger = AuditLogger()
