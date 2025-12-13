"""
Output Guardrail
Checks system outputs for safety violations.
"""

from typing import Dict, Any, List
import re
import logging

try:
    from guardrails import Guard
    from guardrails.hub import ToxicLanguage, DetectPII, BiasCheck
    GUARDRAILS_AVAILABLE = True
except ImportError:
    GUARDRAILS_AVAILABLE = False
    logging.warning("Guardrails AI not available. Install with: pip install guardrails-ai")


class OutputGuardrail:
    """
    Guardrail for checking output safety using Guardrails AI.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize output guardrail.

        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.logger = logging.getLogger("output_guardrail")

        # Initialize Guardrails AI Guard
        if GUARDRAILS_AVAILABLE:
            try:
                self.guard = Guard().use_many(
                    ToxicLanguage(threshold=0.5, validation_method="sentence"),
                    DetectPII(),
                    BiasCheck()
                )
                self.logger.info("Guardrails AI initialized successfully for output validation")
            except Exception as e:
                self.logger.error(f"Failed to initialize Guardrails AI: {e}")
                self.guard = None
        else:
            self.guard = None
            self.logger.warning("Guardrails AI not available, using fallback validation")

    def validate(self, response: str, sources: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Validate output response using Guardrails AI.

        Args:
            response: Generated response to validate
            sources: Optional list of sources used (for fact-checking)

        Returns:
            Validation result with 'valid', 'violations', and 'sanitized_output'
        """
        # Ensure response is a string (handle list or other types)
        if not isinstance(response, str):
            if isinstance(response, list):
                response = "\n".join(str(item) for item in response) if response else ""
            else:
                response = str(response) if response else ""

        violations = []
        sanitized_output = response

        # Extract citation/bibliography sections to identify false positives
        # Citations often contain URLs and author names which are legitimate, not PII
        citation_sections = self._extract_citation_sections(response)

        # Use Guardrails AI if available
        if self.guard:
            try:
                # Truncate response if too long to avoid TensorFlow embedding errors
                # Guardrails AI embedding models typically have a 512 token limit
                # We'll use ~1500 characters as a safe limit (roughly 400 tokens)
                MAX_VALIDATION_LENGTH = 1500
                response_for_validation = response
                was_truncated = False
                if len(response) > MAX_VALIDATION_LENGTH:
                    self.logger.debug(f"Response too long ({len(response)} chars), truncating to {MAX_VALIDATION_LENGTH} chars for Guardrails AI validation")
                    # Truncate but keep the beginning (most important content)
                    response_for_validation = response[:MAX_VALIDATION_LENGTH] + "... [truncated for validation]"
                    was_truncated = True

                # Validate the response (truncated if necessary)
                # We'll filter out false positives from citations afterwards
                result = self.guard.validate(response_for_validation)

                # Check if validation passed
                validation_passed = getattr(result, 'validation_passed', True)
                # Only use validated_output if we didn't truncate (to preserve full response)
                # If truncated, we'll sanitize the original full response based on violations found
                if hasattr(result, 'validated_output') and not was_truncated:
                    # If validated_output exists and we didn't truncate, use it
                    sanitized_output = result.validated_output
                elif hasattr(result, 'validated_output') and was_truncated:
                    # If we truncated, don't use validated_output (it's based on truncated version)
                    # We'll sanitize the original full response later based on violations
                    self.logger.debug("Skipping validated_output from truncated response - will sanitize original full response")

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

                        # Filter out false positives: PII in citation sections (URLs, author names are legitimate in citations)
                        if validator_name == "DetectPII" and self._is_citation_false_positive(error_msg, response):
                            self.logger.debug(f"Ignoring PII false positive in citation section: {error_msg[:100]}")
                            continue

                        # Map validator names to categories
                        category_map = {
                            "ToxicLanguage": "harmful_content",
                            "DetectPII": "personal_attacks",
                            "BiasCheck": "misinformation",
                        }

                        violations.append({
                            "validator": validator_name.lower().replace(" ", "_"),
                            "category": category_map.get(validator_name, "unknown"),
                            "reason": error_msg,
                            "severity": "high" if validator_name in ["ToxicLanguage", "DetectPII"] else "medium"
                        })

            except Exception as e:
                # If it's a TensorFlow/embedding error (usually due to text being too long),
                # log as warning and continue with fallback checks
                error_str = str(e).lower()
                if "tensorflow" in error_str or "embedding" in error_str or "indices" in error_str or "invalid_argument" in error_str:
                    self.logger.warning(f"Guardrails AI validation skipped (text too long or embedding error): {str(e)[:200]}")
                    self.logger.warning("Using fallback validation methods only")
                else:
                    # For other unexpected errors, log as error
                    self.logger.error(f"Guardrails AI validation error: {e}")
                # Fallback to basic checks
                pass

        # Additional checks using helper methods
        # Check PII in full response (fallback method)
        pii_violations = self._check_pii(response)
        violations.extend(pii_violations)

        # Check citations separately with more lenient rules (only flag obvious PII like emails)
        if citation_sections:
            citation_pii_violations = self._check_citation_pii(citation_sections)
            violations.extend(citation_pii_violations)

        harmful_violations = self._check_harmful_content(response)
        violations.extend(harmful_violations)

        bias_violations = self._check_bias(response)
        violations.extend(bias_violations)

        if sources:
            consistency_violations = self._check_factual_consistency(response, sources)
            violations.extend(consistency_violations)

        # Sanitize if violations found
        if violations:
            sanitized_output = self._sanitize(response, violations)

        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "sanitized_output": sanitized_output
        }

    def _check_pii(self, text: str) -> List[Dict[str, Any]]:
        """
        Check for personally identifiable information (fallback method).
        Main validation is done through Guard.validate().

        Args:
            text: Text to check

        Returns:
            List of violations if PII detected
        """
        violations = []

        # Fallback: Simple regex patterns for common PII
        patterns = {
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        }

        for pii_type, pattern in patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                violations.append({
                    "validator": "detect_pii",
                    "pii_type": pii_type,
                    "category": "personal_attacks",
                    "reason": f"Contains {pii_type}",
                    "severity": "high",
                    "matches": matches
                })

        return violations

    def _extract_citation_sections(self, text: str) -> str:
        """
        Extract citation/bibliography sections from text.

        Args:
            text: Full text response

        Returns:
            Extracted citation sections
        """
        # Look for common citation section markers
        citation_patterns = [
            r'(?i)(?:References|Bibliography|Works Cited|Citations?)(?:\s*:)?\s*\n(.*?)(?=\n\n|\Z)',
            r'(?i)(?:References|Bibliography|Works Cited|Citations?)(?:\s*:)?\s*\n(.*)',
        ]

        citation_text = ""
        for pattern in citation_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            if matches:
                citation_text = "\n".join(matches)
                break

        return citation_text

    def _remove_citation_sections(self, text: str) -> str:
        """
        Remove citation/bibliography sections from text for validation.

        Args:
            text: Full text response

        Returns:
            Text with citation sections removed
        """
        # Remove citation sections marked by common headers
        citation_patterns = [
            r'(?i)(?:References|Bibliography|Works Cited|Citations?)(?:\s*:)?\s*\n.*',
        ]

        cleaned_text = text
        for pattern in citation_patterns:
            cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.DOTALL)

        return cleaned_text.strip()

    def _is_citation_false_positive(self, error_msg: str, full_text: str) -> bool:
        """
        Check if a PII error is a false positive from citation sections.
        URLs and author names in citations are legitimate, not PII.

        Args:
            error_msg: Error message from Guardrails AI
            full_text: Full response text

        Returns:
            True if this appears to be a false positive from citations
        """
        # Check if error mentions URLs or common citation patterns
        citation_indicators = [
            "http", "https", "www.", ".com", ".org", ".net", ".edu",
            "doi:", "author", "journal", "conference", "bibliography", "references"
        ]

        error_lower = error_msg.lower()
        text_lower = full_text.lower()

        # If error mentions URL patterns and text contains citation sections
        if any(indicator in error_lower for indicator in ["http", "url", "link", "domain"]):
            # Check if this is in a citation/bibliography section
            citation_section = self._extract_citation_sections(full_text)
            if citation_section and len(citation_section) > 50:  # Substantial citation section
                # Check if the error text appears in citation section
                if any(indicator in citation_section.lower() for indicator in citation_indicators):
                    return True

        return False

    def _check_citation_pii(self, citation_text: str) -> List[Dict[str, Any]]:
        """
        Check for PII in citations with more lenient rules.
        URLs and author names in citations are typically legitimate.

        Args:
            citation_text: Citation/bibliography text

        Returns:
            List of violations (should be minimal for citations)
        """
        violations = []

        if not citation_text:
            return violations

        # Only flag obvious PII in citations (emails, phone numbers, SSNs)
        # URLs and author names are expected in citations
        patterns = {
            "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            "phone": r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
            "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
        }

        for pii_type, pattern in patterns.items():
            matches = re.findall(pattern, citation_text)
            if matches:
                violations.append({
                    "validator": "detect_pii",
                    "pii_type": pii_type,
                    "category": "personal_attacks",
                    "reason": f"Contains {pii_type} in citations",
                    "severity": "medium",  # Lower severity for citations
                    "matches": matches
                })

        return violations

    def _check_harmful_content(self, text: str) -> List[Dict[str, Any]]:
        """
        Check for harmful or inappropriate content (fallback method).
        Main validation is done through Guard.validate().

        Args:
            text: Text to check

        Returns:
            List of violations if harmful content detected
        """
        violations = []

        # Fallback: Basic keyword check
        harmful_keywords = ["violent", "harmful", "dangerous"]
        for keyword in harmful_keywords:
            if keyword in text.lower():
                violations.append({
                    "validator": "toxic_language",
                    "category": "harmful_content",
                    "reason": f"May contain harmful content: {keyword}",
                    "severity": "medium"
                })

        return violations

    def _check_factual_consistency(
        self,
        response: str,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Check if response is consistent with sources.

        TODO: YOUR CODE HERE Implement fact-checking logic
        This could use LLM-based verification
        """
        violations = []

        # Placeholder - this is complex and could use LLM
        # to verify claims against sources

        return violations

    def _check_bias(self, text: str) -> List[Dict[str, Any]]:
        """
        Check for biased language (fallback method).
        Main validation is done through Guard.validate() with BiasCheck.

        Args:
            text: Text to check

        Returns:
            List of violations if bias detected
        """
        violations = []
        # Main bias checking is done through Guard.validate()
        # This is a placeholder for additional custom checks if needed
        return violations

    def _sanitize(self, text: str, violations: List[Dict[str, Any]]) -> str:
        """
        Sanitize text by removing/redacting violations.

        Args:
            text: Text to sanitize
            violations: List of violations to address

        Returns:
            Sanitized text
        """
        sanitized = text
        redaction_marker = "[REDACTED]"

        # Redact PII
        for violation in violations:
            validator_name = violation.get("validator", "")

            if validator_name in ["detect_pii", "pii"]:
                # Redact PII matches
                matches = violation.get("matches", [])
                for match in matches:
                    sanitized = sanitized.replace(match, redaction_marker)

            elif validator_name == "toxic_language":
                # For toxic language, we might want to remove sentences
                # This is a simple implementation - could be enhanced
                # For now, we rely on Guardrails AI sanitized output if available
                pass

            elif validator_name == "bias_check":
                # For bias, we might want to flag but not necessarily redact
                # Could add a warning marker
                pass

        return sanitized
