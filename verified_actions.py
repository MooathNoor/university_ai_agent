from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional


VALID_FINAL_STATUSES = {"success", "failed", "unknown", "blocked"}
VALID_EXECUTION_STATUSES = {"executed", "failed", "unknown"}
VALID_VERIFICATION_STATUSES = {"verified", "failed", "unknown", "not_run"}


@dataclass
class ActionSpec:
    """
    Definition of one state-changing action.

    executor:
        Performs the real state-changing operation.

    verifier:
        Re-reads the external system AFTER execution and verifies the resulting
        state from fresh evidence. It must not trust the executor's own claim.

    requires_authorization:
        The caller must explicitly authorize the action before execution.

    requires_presence:
        Reserved for actions such as attendance where truthful physical presence
        is a required precondition.
    """

    action_type: str
    executor: Callable[[Dict[str, Any]], Dict[str, Any]]
    verifier: Callable[[Dict[str, Any]], Dict[str, Any]]
    requires_authorization: bool = True
    requires_presence: bool = False


@dataclass
class VerifiedActionResult:
    action_type: str
    status: str
    execution_status: str
    verification_status: str
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    execution_result: Dict[str, Any] = field(default_factory=dict)
    verification_result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_type": self.action_type,
            "status": self.status,
            "execution_status": self.execution_status,
            "verification_status": self.verification_status,
            "message": self.message,
            "evidence": dict(self.evidence),
            "execution_result": dict(self.execution_result),
            "verification_result": dict(self.verification_result),
        }


class VerifiedActionRunner:
    """
    Generic execution gate for state-changing actions.

    Core rule:
        execution success is NEVER enough to report success.

    A final ``success`` is returned only when the verifier independently
    re-reads the external system and returns ``status="verified"``.

    This module intentionally contains no Moodle-specific POST logic. Moodle
    actions are registered later with real executors and fresh-state verifiers.
    """

    def __init__(self):
        self._actions: Dict[str, ActionSpec] = {}

    def register(
        self,
        action_type: str,
        executor: Callable[[Dict[str, Any]], Dict[str, Any]],
        verifier: Callable[[Dict[str, Any]], Dict[str, Any]],
        *,
        requires_authorization: bool = True,
        requires_presence: bool = False,
    ) -> None:
        action_type = str(action_type or "").strip()

        if not action_type:
            raise ValueError("action_type is required.")

        if not callable(executor):
            raise TypeError("executor must be callable.")

        if not callable(verifier):
            raise TypeError("verifier must be callable.")

        self._actions[action_type] = ActionSpec(
            action_type=action_type,
            executor=executor,
            verifier=verifier,
            requires_authorization=bool(requires_authorization),
            requires_presence=bool(requires_presence),
        )

    def is_registered(self, action_type: str) -> bool:
        return str(action_type or "").strip() in self._actions

    def registered_actions(self):
        return sorted(self._actions.keys())

    @staticmethod
    def _normalize_execution_result(result: Any) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return {
                "status": "unknown",
                "message": "Executor returned an invalid result.",
            }

        normalized = dict(result)
        status = str(normalized.get("status", "unknown")).strip().lower()

        aliases = {
            "success": "executed",
            "ok": "executed",
            "sent": "executed",
            "done": "executed",
            "error": "failed",
            "failure": "failed",
        }

        status = aliases.get(status, status)
        if status not in VALID_EXECUTION_STATUSES:
            status = "unknown"

        normalized["status"] = status
        return normalized

    @staticmethod
    def _normalize_verification_result(result: Any) -> Dict[str, Any]:
        if not isinstance(result, dict):
            return {
                "status": "unknown",
                "message": "Verifier returned an invalid result.",
            }

        normalized = dict(result)
        status = str(normalized.get("status", "unknown")).strip().lower()

        aliases = {
            "success": "verified",
            "ok": "verified",
            "confirmed": "verified",
            "match": "verified",
            "error": "unknown",
            "failure": "failed",
            "mismatch": "failed",
        }

        status = aliases.get(status, status)
        if status not in {"verified", "failed", "unknown"}:
            status = "unknown"

        normalized["status"] = status
        return normalized

    @staticmethod
    def _blocked_result(action_type: str, message: str) -> VerifiedActionResult:
        return VerifiedActionResult(
            action_type=action_type,
            status="blocked",
            execution_status="unknown",
            verification_status="not_run",
            message=message,
        )

    def run(
        self,
        action_type: str,
        payload: Optional[Dict[str, Any]] = None,
        *,
        authorized: bool = False,
        presence_confirmed: bool = False,
    ) -> VerifiedActionResult:
        action_type = str(action_type or "").strip()
        payload = dict(payload or {})

        spec = self._actions.get(action_type)
        if spec is None:
            return self._blocked_result(
                action_type,
                f"Action '{action_type}' is not registered.",
            )

        if spec.requires_authorization and not authorized:
            return self._blocked_result(
                action_type,
                "Explicit authorization is required before this action can run.",
            )

        if spec.requires_presence and not presence_confirmed:
            return self._blocked_result(
                action_type,
                "Confirmed physical presence is required before this action can run.",
            )

        # ------------------------------------------------------------
        # 1) Execute
        # ------------------------------------------------------------
        try:
            raw_execution = spec.executor(dict(payload))
        except Exception as error:
            return VerifiedActionResult(
                action_type=action_type,
                status="failed",
                execution_status="failed",
                verification_status="not_run",
                message=f"Action execution raised an error: {error}",
                execution_result={
                    "status": "failed",
                    "error": str(error),
                },
            )

        execution = self._normalize_execution_result(raw_execution)
        execution_status = execution["status"]

        if execution_status == "failed":
            return VerifiedActionResult(
                action_type=action_type,
                status="failed",
                execution_status="failed",
                verification_status="not_run",
                message=execution.get(
                    "message",
                    "The action could not be executed.",
                ),
                execution_result=execution,
            )

        if execution_status == "unknown":
            # Never verify/report success when we cannot even establish whether
            # the mutation request was accepted/executed.
            return VerifiedActionResult(
                action_type=action_type,
                status="unknown",
                execution_status="unknown",
                verification_status="not_run",
                message=execution.get(
                    "message",
                    "The execution result is uncertain, so success cannot be claimed.",
                ),
                execution_result=execution,
            )

        # ------------------------------------------------------------
        # 2) Verify from fresh external state
        # ------------------------------------------------------------
        verification_payload = dict(payload)
        verification_payload["_execution_result"] = dict(execution)

        try:
            raw_verification = spec.verifier(verification_payload)
        except Exception as error:
            return VerifiedActionResult(
                action_type=action_type,
                status="unknown",
                execution_status="executed",
                verification_status="unknown",
                message=(
                    "The action was executed, but verification failed with an "
                    f"error: {error}"
                ),
                execution_result=execution,
                verification_result={
                    "status": "unknown",
                    "error": str(error),
                },
            )

        verification = self._normalize_verification_result(raw_verification)
        verification_status = verification["status"]
        evidence = verification.get("evidence")
        if not isinstance(evidence, dict):
            evidence = {}

        # ------------------------------------------------------------
        # 3) Report final state
        # ------------------------------------------------------------
        if verification_status == "verified":
            return VerifiedActionResult(
                action_type=action_type,
                status="success",
                execution_status="executed",
                verification_status="verified",
                message=verification.get(
                    "message",
                    "Action completed and was verified from fresh external state.",
                ),
                evidence=evidence,
                execution_result=execution,
                verification_result=verification,
            )

        if verification_status == "failed":
            return VerifiedActionResult(
                action_type=action_type,
                status="failed",
                execution_status="executed",
                verification_status="failed",
                message=verification.get(
                    "message",
                    "The requested state was not verified after execution.",
                ),
                evidence=evidence,
                execution_result=execution,
                verification_result=verification,
            )

        return VerifiedActionResult(
            action_type=action_type,
            status="unknown",
            execution_status="executed",
            verification_status="unknown",
            message=verification.get(
                "message",
                "The action was executed, but Moodle did not expose enough fresh evidence to verify the result.",
            ),
            evidence=evidence,
            execution_result=execution,
            verification_result=verification,
        )
