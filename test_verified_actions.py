from verified_actions import VerifiedActionRunner


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")


assertions = 0


def ok(condition, message):
    global assertions
    check(condition, message)
    assertions += 1


# ============================================================
# 1. Registration
# ============================================================

runner = VerifiedActionRunner()

runner.register(
    "demo_action",
    executor=lambda payload: {
        "status": "executed",
        "request_id": "req-1",
    },
    verifier=lambda payload: {
        "status": "verified",
        "message": "Fresh state matches the requested result.",
        "evidence": {
            "source": "fresh_read",
            "state": "expected",
        },
    },
)

ok(runner.is_registered("demo_action"), "registered action is visible")
ok(runner.registered_actions() == ["demo_action"], "registered action list is stable")


# ============================================================
# 2. Authorization guard
# ============================================================

result = runner.run("demo_action", {"value": 1}, authorized=False)

ok(result.status == "blocked", "unauthorized action is blocked")
ok(result.verification_status == "not_run", "blocked action never reaches verifier")


# ============================================================
# 3. Verified success
# ============================================================

result = runner.run("demo_action", {"value": 1}, authorized=True)

ok(result.status == "success", "final success requires verification")
ok(result.execution_status == "executed", "execution success is recorded")
ok(result.verification_status == "verified", "fresh verification is recorded")
ok(result.evidence.get("source") == "fresh_read", "verification evidence is preserved")


# ============================================================
# 4. Execution failure
# ============================================================

failure_runner = VerifiedActionRunner()
verifier_calls = {"count": 0}


def should_not_run(payload):
    verifier_calls["count"] += 1
    return {"status": "verified"}


failure_runner.register(
    "failure",
    executor=lambda payload: {
        "status": "failed",
        "message": "Remote system rejected the mutation.",
    },
    verifier=should_not_run,
)

result = failure_runner.run("failure", authorized=True)

ok(result.status == "failed", "execution failure becomes final failure")
ok(result.verification_status == "not_run", "failed execution is not falsely verified")
ok(verifier_calls["count"] == 0, "verifier is not called after execution failure")


# ============================================================
# 5. Unknown execution state
# ============================================================

unknown_execution = VerifiedActionRunner()
unknown_execution.register(
    "unknown_execution",
    executor=lambda payload: {"status": "unknown"},
    verifier=lambda payload: {"status": "verified"},
)

result = unknown_execution.run("unknown_execution", authorized=True)

ok(result.status == "unknown", "uncertain execution never becomes success")
ok(result.verification_status == "not_run", "unknown execution stops before verification")


# ============================================================
# 6. Verification mismatch
# ============================================================

mismatch_runner = VerifiedActionRunner()
mismatch_runner.register(
    "mismatch",
    executor=lambda payload: {"status": "executed"},
    verifier=lambda payload: {
        "status": "failed",
        "message": "Fresh state does not match requested state.",
        "evidence": {"actual": "old_state"},
    },
)

result = mismatch_runner.run("mismatch", authorized=True)

ok(result.status == "failed", "fresh-state mismatch becomes final failure")
ok(result.execution_status == "executed", "mismatch retains execution outcome")
ok(result.verification_status == "failed", "mismatch is explicit verification failure")
ok(result.evidence.get("actual") == "old_state", "mismatch evidence is preserved")


# ============================================================
# 7. Verification unknown
# ============================================================

unknown_verify = VerifiedActionRunner()
unknown_verify.register(
    "unknown_verify",
    executor=lambda payload: {"status": "executed"},
    verifier=lambda payload: {
        "status": "unknown",
        "message": "Moodle did not expose enough evidence.",
    },
)

result = unknown_verify.run("unknown_verify", authorized=True)

ok(result.status == "unknown", "inconclusive verification never reports success")
ok(result.verification_status == "unknown", "verification uncertainty is preserved")


# ============================================================
# 8. Executor exception
# ============================================================

exception_runner = VerifiedActionRunner()


def exploding_executor(payload):
    raise RuntimeError("network mutation failed")


exception_runner.register(
    "executor_exception",
    executor=exploding_executor,
    verifier=lambda payload: {"status": "verified"},
)

result = exception_runner.run("executor_exception", authorized=True)

ok(result.status == "failed", "executor exception becomes failure")
ok(result.verification_status == "not_run", "executor exception does not run verifier")


# ============================================================
# 9. Verifier exception
# ============================================================

verify_exception_runner = VerifiedActionRunner()


def exploding_verifier(payload):
    raise RuntimeError("fresh read failed")


verify_exception_runner.register(
    "verify_exception",
    executor=lambda payload: {"status": "executed"},
    verifier=exploding_verifier,
)

result = verify_exception_runner.run("verify_exception", authorized=True)

ok(result.status == "unknown", "verifier exception becomes unknown, not success")
ok(result.execution_status == "executed", "verifier exception preserves executed state")
ok(result.verification_status == "unknown", "verifier exception records unknown verification")


# ============================================================
# 10. Presence guard
# ============================================================

presence_calls = {"executor": 0}


def presence_executor(payload):
    presence_calls["executor"] += 1
    return {"status": "executed"}


presence_runner = VerifiedActionRunner()
presence_runner.register(
    "attendance_like_action",
    executor=presence_executor,
    verifier=lambda payload: {"status": "verified"},
    requires_authorization=True,
    requires_presence=True,
)

result = presence_runner.run(
    "attendance_like_action",
    authorized=True,
    presence_confirmed=False,
)

ok(result.status == "blocked", "presence-sensitive action is blocked without presence confirmation")
ok(presence_calls["executor"] == 0, "presence guard blocks before mutation")

result = presence_runner.run(
    "attendance_like_action",
    authorized=True,
    presence_confirmed=True,
)

ok(result.status == "success", "presence-sensitive action can run after confirmation")
ok(presence_calls["executor"] == 1, "presence-confirmed action executes exactly once")


# ============================================================
# 11. Unregistered action
# ============================================================

result = runner.run("not_registered", authorized=True)

ok(result.status == "blocked", "unregistered state-changing action fails closed")


# ============================================================
# 12. Aliases normalize safely
# ============================================================

alias_runner = VerifiedActionRunner()
alias_runner.register(
    "alias_test",
    executor=lambda payload: {"status": "success"},
    verifier=lambda payload: {"status": "confirmed"},
)

result = alias_runner.run("alias_test", authorized=True)

ok(result.status == "success", "safe executor/verifier status aliases normalize correctly")


print()
print(f"PASS: {assertions} Phase 4C verified-action assertions")
