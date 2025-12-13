"""
Safety Manager
Coordinates safety guardrails and logs safety events.
"""

from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
import json

from .input_guardrail import InputGuardrail
from .output_guardrail import OutputGuardrail


class SafetyManager:
    """
    Manages safety guardrails for the multi-agent system.
    Coordinates InputGuardrail and OutputGuardrail using Guardrails AI.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize safety manager.

        Args:
            config: Safety configuration (should include system config for topic)
        """
        self.config = config
        self.enabled = config.get("enabled", True)
        self.log_events = config.get("log_events", True)
        self.logger = logging.getLogger("safety")

        # Safety event log
        self.safety_events: List[Dict[str, Any]] = []

        # Prohibited categories
        self.prohibited_categories = config.get("prohibited_categories", [
            "harmful_content",
            "personal_attacks",
            "misinformation",
            "off_topic_queries"
        ])

        # Response strategies configuration
        self.response_strategies = config.get("response_strategies", {})
        self.on_violation = config.get("on_violation", {})

        # Initialize guardrails
        if self.enabled:
            try:
                # Create full config dict for guardrails (include system config)
                guardrail_config = {
                    "system": config.get("system", {}),
                    **config
                }
                self.input_guardrail = InputGuardrail(guardrail_config)
                self.output_guardrail = OutputGuardrail(guardrail_config)
                self.logger.info("Guardrails initialized successfully")
            except Exception as e:
                self.logger.error(f"Failed to initialize guardrails: {e}")
                self.input_guardrail = None
                self.output_guardrail = None
        else:
            self.input_guardrail = None
            self.output_guardrail = None

    def check_input_safety(self, query: str) -> Dict[str, Any]:
        """
        Check if input query is safe to process.

        Args:
            query: User query to check

        Returns:
            Dictionary with 'safe' boolean, 'violations' list, and optional 'sanitized_query'
        """
        if not self.enabled or not self.input_guardrail:
            return {"safe": True}

        # Validate using InputGuardrail
        validation_result = self.input_guardrail.validate(query)

        violations = validation_result.get("violations", [])
        sanitized_query = validation_result.get("sanitized_input", query)
        is_safe = validation_result.get("valid", True)

        # Apply response strategy based on violations
        if violations:
            strategy_result = self._apply_strategy(violations, query, "input")

            # Update based on strategy
            if strategy_result.get("action") == "refuse":
                is_safe = False
                sanitized_query = None
            elif strategy_result.get("action") == "sanitize":
                sanitized_query = strategy_result.get("sanitized_content", sanitized_query)
            elif strategy_result.get("action") == "redirect":
                # For redirect, we still mark as unsafe but allow with message
                is_safe = False
                sanitized_query = None

        # Log safety event
        if not is_safe and self.log_events:
            self._log_safety_event("input", query, violations, is_safe)

        # Get strategy message if violations exist
        strategy_message = None
        if violations:
            strategy_result = self._apply_strategy(violations, query, "input")
            strategy_message = strategy_result.get("message")

        result = {
            "safe": is_safe,
            "violations": violations
        }

        if sanitized_query:
            result["sanitized_query"] = sanitized_query

        # Always include message if available (especially for refused queries)
        if strategy_message:
            result["message"] = strategy_message

        return result

    def check_output_safety(self, response: str) -> Dict[str, Any]:
        """
        Check if output response is safe to return.

        Args:
            response: Generated response to check

        Returns:
            Dictionary with 'safe' boolean, 'violations' list, and 'response' (sanitized or refusal message)
        """
        if not self.enabled or not self.output_guardrail:
            return {"safe": True, "response": response}

        # Validate using OutputGuardrail
        validation_result = self.output_guardrail.validate(response)

        violations = validation_result.get("violations", [])
        sanitized_output = validation_result.get("sanitized_output", response)
        is_safe = validation_result.get("valid", True)

        # Apply response strategy based on violations
        final_response = response
        if violations:
            strategy_result = self._apply_strategy(violations, response, "output")

            # Update based on strategy
            if strategy_result.get("action") == "refuse":
                is_safe = False
                final_response = strategy_result.get("message",
                    self.on_violation.get("message", "I cannot provide this response due to safety policies."))
            elif strategy_result.get("action") == "sanitize":
                final_response = strategy_result.get("sanitized_content", sanitized_output)
                # Check if sanitization was successful (not too much removed)
                if len(final_response) < len(response) * 0.5:  # If more than 50% removed
                    # Fallback to refuse if configured
                    strategy = self._get_response_strategy(violations[0].get("validator", ""), "output")
                    if strategy.get("fallback_to_refuse", False):
                        is_safe = False
                        final_response = strategy.get("message",
                            self.on_violation.get("message", "I cannot provide this response due to safety policies."))

        # Log safety event
        if not is_safe and self.log_events:
            self._log_safety_event("output", response, violations, is_safe)

        return {
            "safe": is_safe,
            "violations": violations,
            "response": final_response
        }

    def _sanitize_response(self, response: str, violations: List[Dict[str, Any]]) -> str:
        """
        Sanitize response by removing or redacting unsafe content.

        Args:
            response: Response to sanitize
            violations: List of violations to address

        Returns:
            Sanitized response
        """
        # Use OutputGuardrail's sanitization
        if self.output_guardrail:
            return self.output_guardrail._sanitize(response, violations)

        # Fallback sanitization
        sanitized = response
        for violation in violations:
            if violation.get("validator") == "detect_pii":
                matches = violation.get("matches", [])
                for match in matches:
                    sanitized = sanitized.replace(match, "[REDACTED]")

        return sanitized

    def _get_response_strategy(self, validator_name: str, violation_type: str) -> Dict[str, Any]:
        """
        Get response strategy for a specific validator.

        Args:
            validator_name: Name of the validator (e.g., "toxic_language")
            violation_type: "input" or "output"

        Returns:
            Strategy configuration dict
        """
        # Look up in response_strategies config
        strategies = self.response_strategies.get(violation_type, {})
        strategy = strategies.get(validator_name)

        if strategy:
            return strategy

        # Fall back to default
        return self.response_strategies.get("default", {
            "action": self.on_violation.get("action", "refuse"),
            "message": self.on_violation.get("message", "I cannot process this request due to safety policies.")
        })

    def _apply_strategy(
        self,
        violations: List[Dict[str, Any]],
        content: str,
        content_type: str
    ) -> Dict[str, Any]:
        """
        Apply response strategy based on violations.

        Args:
            violations: List of violations
            content: Original content
            content_type: "input" or "output"

        Returns:
            Dict with 'action', 'message', and optionally 'sanitized_content'
        """
        if not violations:
            return {"action": "allow", "message": None}

        # Find highest severity violation
        severity_order = {"high": 3, "medium": 2, "low": 1}
        highest_severity_violation = max(
            violations,
            key=lambda v: severity_order.get(v.get("severity", "low"), 1)
        )

        validator_name = highest_severity_violation.get("validator", "")
        strategy = self._get_response_strategy(validator_name, content_type)

        action = strategy.get("action", "refuse")
        message = strategy.get("message",
            self.on_violation.get("message", "I cannot process this request due to safety policies."))

        result = {
            "action": action,
            "message": message
        }

        # If sanitize, get sanitized content
        if action == "sanitize":
            if content_type == "input" and self.input_guardrail:
                validation_result = self.input_guardrail.validate(content)
                result["sanitized_content"] = validation_result.get("sanitized_input", content)
            elif content_type == "output" and self.output_guardrail:
                validation_result = self.output_guardrail.validate(content)
                result["sanitized_content"] = validation_result.get("sanitized_output", content)
            else:
                result["sanitized_content"] = content

        return result

    def _log_safety_event(
        self,
        event_type: str,
        content: str,
        violations: List[Dict[str, Any]],
        is_safe: bool
    ):
        """
        Log a safety event.

        Args:
            event_type: "input" or "output"
            content: The content that was checked
            violations: List of violations found
            is_safe: Whether content passed safety checks
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "safe": is_safe,
            "violations": violations,
            "content_preview": content[:100] + "..." if len(content) > 100 else content
        }

        self.safety_events.append(event)
        self.logger.warning(f"Safety event: {event_type} - safe={is_safe}")

        # Write to safety log file if configured
        log_file = self.config.get("safety_log_file")
        if log_file and self.log_events:
            try:
                with open(log_file, "a") as f:
                    f.write(json.dumps(event) + "\n")
            except Exception as e:
                self.logger.error(f"Failed to write safety log: {e}")

    def get_safety_events(self) -> List[Dict[str, Any]]:
        """Get all logged safety events."""
        return self.safety_events

    def get_safety_stats(self) -> Dict[str, Any]:
        """
        Get statistics about safety events.

        Returns:
            Dictionary with safety statistics
        """
        total = len(self.safety_events)
        input_events = sum(1 for e in self.safety_events if e["type"] == "input")
        output_events = sum(1 for e in self.safety_events if e["type"] == "output")
        violations = sum(1 for e in self.safety_events if not e["safe"])

        return {
            "total_events": total,
            "input_checks": input_events,
            "output_checks": output_events,
            "violations": violations,
            "violation_rate": violations / total if total > 0 else 0
        }

    def clear_events(self):
        """Clear safety event log."""
        self.safety_events = []
