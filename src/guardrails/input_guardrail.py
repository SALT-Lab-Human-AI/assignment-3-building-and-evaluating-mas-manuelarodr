"""
Input Guardrail
Checks user inputs for safety violations.
"""

from typing import Dict, Any, List
import logging

try:
    from guardrails import Guard
    from guardrails.hub import ToxicLanguage, DetectPII
    # Try to import DetectPromptInjection if available
    try:
        from guardrails.hub import DetectPromptInjection
        PROMPT_INJECTION_AVAILABLE = True
    except ImportError:
        PROMPT_INJECTION_AVAILABLE = False
        logging.warning("DetectPromptInjection not available in guardrails-ai. Using fallback detection.")
    GUARDRAILS_AVAILABLE = True
except ImportError:
    GUARDRAILS_AVAILABLE = False
    PROMPT_INJECTION_AVAILABLE = False
    logging.warning("Guardrails AI not available. Install with: pip install guardrails-ai")


class InputGuardrail:
    """
    Guardrail for checking input safety using Guardrails AI.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize input guardrail.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger("input_guardrail")
        # Get topic from config - handle both nested and flat config structures
        system_config = config.get("system", {})
        if isinstance(system_config, dict):
            self.topic = system_config.get("topic", "Ethical AI in Education")
        else:
            self.topic = "Ethical AI in Education"

        # Initialize Guardrails AI Guard
        if GUARDRAILS_AVAILABLE:
            try:
                validators = [
                    ToxicLanguage(threshold=0.5, validation_method="sentence"),
                    DetectPII()
                ]
                # Add DetectPromptInjection if available
                if PROMPT_INJECTION_AVAILABLE:
                    validators.append(DetectPromptInjection())
                    self.logger.info("DetectPromptInjection validator added")

                self.guard = Guard().use_many(*validators)
                self.logger.info("Guardrails AI initialized successfully for input validation")
            except Exception as e:
                self.logger.error(f"Failed to initialize Guardrails AI: {e}")
                self.guard = None
        else:
            self.guard = None
            self.logger.warning("Guardrails AI not available, using fallback validation")

    def validate(self, query: str) -> Dict[str, Any]:
        """
        Validate input query using Guardrails AI.

        Args:
            query: User input to validate

        Returns:
            Validation result with 'valid', 'violations', and 'sanitized_input'
        """
        violations = []
        sanitized_input = query

        # Basic length checks
        if len(query) < 5:
            violations.append({
                "validator": "length",
                "category": "format",
                "reason": "Query too short",
                "severity": "low"
            })

        if len(query) > 2000:
            violations.append({
                "validator": "length",
                "category": "format",
                "reason": "Query too long",
                "severity": "medium"
            })

        # Use Guardrails AI if available
        if self.guard:
            try:
                result = self.guard.validate(query)

                # Check if validation passed
                validation_passed = getattr(result, 'validation_passed', True)
                if hasattr(result, 'validated_output'):
                    # If validated_output exists, use it
                    sanitized_input = result.validated_output

                if not validation_passed:
                    # Convert Guardrails AI errors to violation format
                    errors = getattr(result, 'errors', [])
                    if not errors:
                        # If no errors list, check for error attribute
                        error = getattr(result, 'error', None)
                        if error:
                            errors = [error]

                    for error in errors:
                        # Handle both dict and string errors
                        if isinstance(error, dict):
                            validator_name = error.get("validator", error.get("name", "unknown"))
                            error_msg = error.get("error", error.get("message", str(error)))
                        else:
                            validator_name = "unknown"
                            error_msg = str(error)

                        # Map validator names to categories and normalize names
                        category_map = {
                            "ToxicLanguage": "harmful_content",
                            "DetectPII": "personal_attacks",
                            "DetectPromptInjection": "harmful_content",
                            "prompt_injection": "harmful_content",  # Fallback name
                        }

                        # Normalize validator name for config lookup
                        normalized_name = validator_name.lower().replace(" ", "_").replace("detect", "").replace("_", "").replace("promptinjection", "prompt_injection")
                        if "prompt" in normalized_name and "injection" in normalized_name:
                            normalized_name = "prompt_injection"
                        elif "toxic" in normalized_name:
                            normalized_name = "toxic_language"
                        elif "pii" in normalized_name:
                            normalized_name = "detect_pii"

                        violations.append({
                            "validator": normalized_name,
                            "category": category_map.get(validator_name, category_map.get(normalized_name, "unknown")),
                            "reason": error_msg,
                            "severity": "high" if validator_name in ["ToxicLanguage", "DetectPromptInjection"] or "prompt_injection" in normalized_name else "medium"
                        })

            except Exception as e:
                self.logger.error(f"Guardrails AI validation error: {e}")
                # Fallback to basic checks
                pass

        # Additional checks using helper methods
        toxic_violations = self._check_toxic_language(query)
        violations.extend(toxic_violations)

        injection_violations = self._check_prompt_injection(query)
        violations.extend(injection_violations)

        relevance_violations = self._check_relevance(query)
        violations.extend(relevance_violations)

        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "sanitized_input": sanitized_input
        }

    def _check_toxic_language(self, text: str) -> List[Dict[str, Any]]:
        """
        Check for toxic/harmful language (fallback method).
        Main validation is done through Guard.validate().

        Args:
            text: Text to check

        Returns:
            List of violations if toxic language detected
        """
        violations = []
        # This is a fallback - main validation happens in validate()
        # Could add basic keyword checks here if needed
        return violations

    def _check_prompt_injection(self, text: str) -> List[Dict[str, Any]]:
        """
        Check for prompt injection attempts (fallback method).
        Main validation is done through Guard.validate().

        Args:
            text: Text to check

        Returns:
            List of violations if prompt injection detected
        """
        violations = []
        text_lower = text.lower()

        # Comprehensive prompt injection patterns
        injection_patterns = [
            # Direct instruction manipulation
            ("ignore previous instructions", "high"),
            ("ignore all previous", "high"),
            ("disregard all previous", "high"),
            ("forget everything", "high"),
            ("forget all previous", "high"),
            ("disregard the above", "high"),
            ("ignore the above", "high"),
            ("override", "high"),
            ("bypass", "high"),

            # System prompt manipulation
            ("system:", "high"),
            ("system prompt:", "high"),
            ("you are now", "high"),
            ("you are a", "high"),
            ("act as", "high"),
            ("pretend to be", "high"),
            ("roleplay as", "high"),

            # Command injection
            ("sudo", "high"),
            ("execute", "high"),
            ("run command", "high"),
            ("run code", "high"),
            ("<script>", "high"),
            ("javascript:", "high"),

            # Instruction injection
            ("new instructions:", "high"),
            ("updated instructions:", "high"),
            ("revised instructions:", "high"),
            ("your new task is", "high"),
            ("your new role is", "high"),

            # Context manipulation
            ("previous conversation", "medium"),
            ("earlier instructions", "medium"),
            ("initial prompt", "medium"),
            ("original prompt", "medium"),

            # Encoding tricks
            ("base64", "medium"),
            ("decode this", "medium"),
            ("translate this", "medium"),
        ]

        for pattern, severity in injection_patterns:
            if pattern in text_lower:
                violations.append({
                    "validator": "prompt_injection",
                    "category": "harmful_content",
                    "reason": f"Potential prompt injection detected: '{pattern}'",
                    "severity": severity,
                    "pattern": pattern
                })
                # Only report the first high-severity match to avoid spam
                if severity == "high":
                    break

        return violations

    def _check_relevance(self, query: str) -> List[Dict[str, Any]]:
        """
        Check if query is relevant to the system's purpose (Ethical AI in Education).

        Args:
            query: Query to check for relevance

        Returns:
            List of violations if query is off-topic
        """
        violations = []

        # Simple keyword-based relevance check
        # The topic is "Ethical AI in Education"
        topic_keywords = [
            "ethical", "ethics", "ai", "artificial intelligence", "education",
            "educational", "learning", "teaching", "pedagogy", "student",
            "bias", "fairness", "transparency", "accountability", "privacy",
            "algorithm", "machine learning", "automated", "assessment"
        ]

        query_lower = query.lower()
        relevant_keywords_found = sum(1 for keyword in topic_keywords if keyword in query_lower)

        # If no relevant keywords found and query is substantial, flag as off-topic
        # Changed >= 3 to catch queries like "are you happy" (3 words)
        if relevant_keywords_found == 0 and len(query.split()) >= 3:
            violations.append({
                "validator": "off_topic",
                "category": "off_topic_queries",
                "reason": f"Query does not appear to be related to '{self.topic}'",
                "severity": "medium"
            })

        return violations
