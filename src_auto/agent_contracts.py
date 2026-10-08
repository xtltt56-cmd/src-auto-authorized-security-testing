"""Finite proposals, not commands. All permission remains in the executor."""
import json
from dataclasses import asdict, dataclass
from typing import Mapping

from .ai import _redact

CATALOG_VERSION = "local-readonly-v4"
ACTIONS = frozenset({"inspect_headers", "inspect_local_route", "analyze_passive_capture", "discover_surface", "inspect_api_schema",
                     "compare_object_authorization", "run_local_regression",
                     "validate_controlled_inputs", "compare_object_authorization_matrix",
                     "compare_business_object", "validate_business_controls",
                     "review_candidate", "read_observation", "finish", "request_human_review"})


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_field")
        result[key] = value
    return result


@dataclass(frozen=True)
class Decision:
    action: str
    reference: str
    evidence: tuple
    reason: str

    @classmethod
    def parse(cls, text, references, observations):
        if not isinstance(text, str) or len(text.encode("utf-8")) > 4096:
            raise ValueError("invalid_decision_size")
        value = json.loads(text, object_pairs_hook=_unique)
        if not isinstance(value, dict) or set(value) != {"action", "reference", "evidence", "reason"}:
            raise ValueError("invalid_decision_fields")
        if not isinstance(value["action"], str) or value["action"] not in ACTIONS:
            raise ValueError("unknown_action")
        if not isinstance(value["reference"], str) or value["reference"] not in references:
            raise ValueError("foreign_reference")
        if value["action"] in {"inspect_headers", "analyze_passive_capture", "discover_surface", "inspect_api_schema", "run_local_regression",
                                "validate_controlled_inputs", "compare_object_authorization_matrix", "validate_business_controls",
                                "finish", "request_human_review"} and value["reference"] != "entry":
            raise ValueError("action_reference_mismatch")
        if value["action"] == "review_candidate" and value["reference"] != "candidate":
            raise ValueError("action_reference_mismatch")
        evidence = value["evidence"]
        if not isinstance(evidence, list) or len(evidence) > 8 or any(not isinstance(x, str) or x not in observations for x in evidence):
            raise ValueError("foreign_evidence")
        reason = value["reason"]
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 240:
            raise ValueError("invalid_reason")
        return cls(value["action"], value["reference"], tuple(evidence), _redact(reason).replace("\n", " "))

    def to_mapping(self):
        return dict(asdict(self), evidence=list(self.evidence))


@dataclass(frozen=True)
class Limits:
    max_steps: int = 8
    max_requests: int = 100
    max_model_calls: int = 12
    max_seconds: int = 900
    max_tokens: int = 20000

    @classmethod
    def from_mapping(cls, value: Mapping):
        upper = cls().to_mapping()
        if not isinstance(value, dict) or set(value) - set(upper):
            raise ValueError("invalid_limits")
        for key, number in value.items():
            if type(number) is not int or not 1 <= number <= upper[key]:
                raise ValueError("invalid_limits")
        return cls(**value)

    def to_mapping(self):
        return asdict(self)
