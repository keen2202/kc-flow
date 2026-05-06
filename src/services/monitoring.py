"""Monitoring, metrics, and alerting system.

Provides:
- Execution metrics collection (duration, tokens, API calls, errors)
- System health monitoring
- Alert rules and notifications
- Prometheus-compatible metrics export
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger()


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Metric:
    """A single metric data point."""
    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class Alert:
    """An alert triggered by a metric threshold."""
    alert_id: str
    name: str
    severity: AlertSeverity
    message: str
    metric_name: str
    metric_value: float
    threshold: float
    triggered_at: str
    resolved_at: str | None = None


@dataclass
class AlertRule:
    """Configuration for an alert rule."""
    name: str
    metric_name: str
    condition: str  # "gt", "lt", "eq", "gte", "lte"
    threshold: float
    severity: AlertSeverity
    message_template: str
    cooldown_seconds: int = 300


class MetricsCollector:
    """Collects and aggregates execution metrics.

    Usage:
        collector = MetricsCollector()
        collector.record_execution("exec_1", "wf_1", duration_ms=1500, tokens=500)
        stats = collector.get_workflow_stats("wf_1")
    """

    def __init__(self) -> None:
        self._metrics: list[Metric] = []
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._alerts: list[Alert] = []
        self._alert_rules: list[AlertRule] = []
        self._last_alert_time: dict[str, float] = {}

    # ── Metric Recording ──

    def record_execution(
        self,
        execution_id: str,
        workflow_id: str,
        duration_ms: int,
        tokens: int = 0,
        api_calls: int = 0,
        status: str = "success",
    ) -> None:
        """Record metrics for a workflow execution."""
        labels = {"workflow_id": workflow_id, "status": status}

        self._record("workflow_execution_total", 1, labels)
        self._record("workflow_execution_duration_ms", duration_ms, labels)
        self._record("workflow_tokens_total", tokens, labels)
        self._record("workflow_api_calls_total", api_calls, labels)

        if status == "failed":
            self._record("workflow_errors_total", 1, labels)

    def record_node_execution(
        self,
        node_id: str,
        node_type: str,
        duration_ms: int,
        status: str = "succeeded",
    ) -> None:
        """Record metrics for a single node execution."""
        labels = {"node_type": node_type, "status": status}
        self._record("node_execution_total", 1, labels)
        self._record("node_execution_duration_ms", duration_ms, labels)

    def record_llm_call(
        self,
        model: str,
        duration_ms: int,
        tokens_in: int,
        tokens_out: int,
    ) -> None:
        """Record metrics for an LLM API call."""
        labels = {"model": model}
        self._record("llm_call_total", 1, labels)
        self._record("llm_call_duration_ms", duration_ms, labels)
        self._record("llm_tokens_input", tokens_in, labels)
        self._record("llm_tokens_output", tokens_out, labels)

    def increment(self, name: str, value: float = 1, labels: dict[str, str] | None = None) -> None:
        """Increment a counter metric."""
        key = self._metric_key(name, labels)
        self._counters[key] += value

    def gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Set a gauge metric."""
        key = self._metric_key(name, labels)
        self._gauges[key] = value

    def histogram(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """Record a histogram value."""
        key = self._metric_key(name, labels)
        self._histograms[key].append(value)

    def _record(self, name: str, value: float, labels: dict[str, str]) -> None:
        """Record a metric data point."""
        self._metrics.append(Metric(name=name, value=value, labels=labels))
        self._check_alert_rules(name, value, labels)

    def _metric_key(self, name: str, labels: dict[str, str] | None) -> str:
        """Generate a unique key for a metric with labels."""
        if labels:
            label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
            return f"{name}{{{label_str}}}"
        return name

    # ── Querying ──

    def get_workflow_stats(self, workflow_id: str) -> dict[str, Any]:
        """Get aggregated stats for a workflow."""
        executions = [m for m in self._metrics if m.name == "workflow_execution_total" and m.labels.get("workflow_id") == workflow_id]
        durations = [m for m in self._metrics if m.name == "workflow_execution_duration_ms" and m.labels.get("workflow_id") == workflow_id]
        tokens = [m for m in self._metrics if m.name == "workflow_tokens_total" and m.labels.get("workflow_id") == workflow_id]

        total = len(executions)
        failed = sum(1 for m in executions if m.labels.get("status") == "failed")
        duration_values = [m.value for m in durations]
        token_values = [m.value for m in tokens]

        return {
            "workflow_id": workflow_id,
            "total_executions": total,
            "failed_executions": failed,
            "success_rate": (total - failed) / total if total > 0 else 0,
            "avg_duration_ms": sum(duration_values) / len(duration_values) if duration_values else 0,
            "p95_duration_ms": sorted(duration_values)[int(len(duration_values) * 0.95)] if duration_values else 0,
            "total_tokens": sum(token_values),
            "avg_tokens": sum(token_values) / len(token_values) if token_values else 0,
        }

    def get_system_stats(self) -> dict[str, Any]:
        """Get overall system statistics."""
        total_execs = sum(m.value for m in self._metrics if m.name == "workflow_execution_total")
        failed_execs = sum(m.value for m in self._metrics if m.name == "workflow_errors_total")
        total_tokens = sum(m.value for m in self._metrics if m.name == "workflow_tokens_total")
        total_api_calls = sum(m.value for m in self._metrics if m.name == "llm_call_total")

        return {
            "total_executions": total_execs,
            "failed_executions": failed_execs,
            "success_rate": (total_execs - failed_execs) / total_execs if total_execs > 0 else 0,
            "total_tokens": total_tokens,
            "total_llm_calls": total_api_calls,
            "active_alerts": len([a for a in self._alerts if a.resolved_at is None]),
        }

    # ── Alerting ──

    def add_alert_rule(self, rule: AlertRule) -> None:
        """Add an alert rule."""
        self._alert_rules.append(rule)

    def _check_alert_rules(self, metric_name: str, value: float, labels: dict[str, str]) -> None:
        """Check if any alert rules are triggered."""
        for rule in self._alert_rules:
            if rule.metric_name != metric_name:
                continue

            # Check cooldown
            last_alert = self._last_alert_time.get(rule.name, 0)
            if time.time() - last_alert < rule.cooldown_seconds:
                continue

            triggered = False
            if rule.condition == "gt" and value > rule.threshold:
                triggered = True
            elif rule.condition == "lt" and value < rule.threshold:
                triggered = True
            elif rule.condition == "gte" and value >= rule.threshold:
                triggered = True
            elif rule.condition == "lte" and value <= rule.threshold:
                triggered = True
            elif rule.condition == "eq" and value == rule.threshold:
                triggered = True

            if triggered:
                alert = Alert(
                    alert_id=f"alert_{int(time.time())}_{rule.name}",
                    name=rule.name,
                    severity=rule.severity,
                    message=rule.message_template.format(value=value, threshold=rule.threshold),
                    metric_name=metric_name,
                    metric_value=value,
                    threshold=rule.threshold,
                    triggered_at=datetime.now(timezone.utc).isoformat(),
                )
                self._alerts.append(alert)
                self._last_alert_time[rule.name] = time.time()

                logger.warning(
                    "Alert triggered",
                    alert_name=rule.name,
                    severity=rule.severity.value,
                    message=alert.message,
                )

    def get_active_alerts(self) -> list[Alert]:
        """Get all active (unresolved) alerts."""
        return [a for a in self._alerts if a.resolved_at is None]

    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.resolved_at = datetime.now(timezone.utc).isoformat()
                return True
        return False

    # ── Prometheus Export ──

    def export_prometheus(self) -> str:
        """Export metrics in Prometheus text format."""
        lines: list[str] = []

        # Counters
        for key, value in self._counters.items():
            lines.append(f"# TYPE {key.split('{')[0]} counter")
            lines.append(f"{key} {value}")

        # Gauges
        for key, value in self._gauges.items():
            lines.append(f"# TYPE {key.split('{')[0]} gauge")
            lines.append(f"{key} {value}")

        # Histograms
        for key, values in self._histograms.items():
            name = key.split('{')[0]
            lines.append(f"# TYPE {name} histogram")
            lines.append(f"{name}_count{{{key.split('{')[1].rstrip('}')}}} {len(values)}")
            lines.append(f"{name}_sum{{{key.split('{')[1].rstrip('}')}}} {sum(values)}")

        return "\n".join(lines)


# Global singleton
metrics_collector = MetricsCollector()
