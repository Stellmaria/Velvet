#!/usr/bin/env python3
"""Fail-closed readiness and evidence policy for Kael reviews."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import PurePath
import re
from typing import Collection, Mapping


class ReadinessStage(StrEnum):
    IMPLEMENTED_BY_CODER = "implemented_by_coder"
    REVIEW_PENDING = "review_pending"
    REVIEW_CHANGES_REQUESTED = "review_changes_requested"
    REVIEW_APPROVED = "review_approved"
    MERGE_AUTHORIZED = "merge_authorized"
    MERGED = "merged"
    ROLLOUT_PENDING = "rollout_pending"
    ROLLOUT_VERIFIED = "rollout_verified"
    COMPLETED = "completed"


class EvidenceLevel(IntEnum):
    AGENT_REPORT = 1
    SOURCE_MARKER = 2
    STATIC_CONTRACT = 3
    UNIT_BEHAVIOR = 4
    INTEGRATION_PUBLIC_INTERFACE = 5
    REAL_CONTAINER_EXECUTION = 6
    HOST_RUNTIME_ACCEPTANCE = 7


class ReviewStatus(StrEnum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    BLOCKED = "blocked"


TRUSTED_LEDGER_FIELDS = frozenset(
    {
        "task_id",
        "run_id",
        "requested_tier",
        "selected_primary_model",
        "selected_provider_route",
        "actual_route",
        "attempted_routes",
        "fallback_reason",
        "workspace_path",
        "workspace_source_ref",
        "baseline_head",
        "final_head",
        "head_changed",
        "branch_changed",
        "refs_changed",
        "working_tree_changed",
        "base_workspace_changed",
        "execution_started",
        "push_or_pr_observed",
        "mutation_started",
    }
)


@dataclass(frozen=True)
class ReviewRequest:
    coder_stage: str
    ci_green: bool
    high_risk: bool
    changed_files: frozenset[str]
    required_files: frozenset[str]
    findings: tuple[str, ...] = ()
    rollout_only_checks: tuple[str, ...] = ()
    protocol_changed: bool = False
    integration_results: tuple["TrustedCheck", ...] = ()
    required_integration_checks: tuple[str, ...] = ()
    review_fix_iterations: int = 0
    ledger: Mapping[str, object] | None = None
    github_mutation_observed: bool = False
    process_cwd: str = ""
    base_workspace: str = ""


@dataclass(frozen=True)
class ReviewDecision:
    status: ReviewStatus
    stage: ReadinessStage
    verified_facts: tuple[str, ...]
    agent_claims_not_independently_verified: tuple[str, ...]
    review_findings: tuple[str, ...]
    rollout_only_checks: tuple[str, ...]
    recommended_next_action: str
    evidence_conflict: bool = False
    delegate_fix: bool = False


@dataclass(frozen=True)
class TrustedCheck:
    name: str
    status: str
    conclusion: str
    source: str = "github-check-run"

    @property
    def successful(self) -> bool:
        return (
            self.source == "github-check-run"
            and self.status == "completed"
            and self.conclusion in {"success", "neutral", "skipped"}
        )


def evidence_satisfies(
    available: Collection[EvidenceLevel], required: EvidenceLevel
) -> bool:
    """Evidence may prove only claims at its own or a weaker level."""

    return any(level >= required for level in available)


def readiness_after_coder(coder_stage: str, *, ci_green: bool) -> ReadinessStage:
    """CI result never bypasses the independent review stage."""

    del ci_green
    if coder_stage != ReadinessStage.IMPLEMENTED_BY_CODER:
        raise ValueError("coder has not reached implemented_by_coder")
    return ReadinessStage.REVIEW_PENDING


_MUTATION_SIGNALS = (
        "head_changed",
        "branch_changed",
        "refs_changed",
        "working_tree_changed",
        "base_workspace_changed",
        "execution_started",
        "push_or_pr_observed",
)


def audit_ledger(ledger: Mapping[str, object]) -> tuple[bool, tuple[str, ...]]:
    findings: list[str] = []
    for field in _MUTATION_SIGNALS + ("mutation_started",):
        if field not in ledger:
            findings.append(f"ledger evidence field missing: {field}")
        elif type(ledger[field]) is not bool:
            findings.append(f"ledger evidence field is not boolean: {field}")

    baseline = ledger.get("baseline_head")
    final = ledger.get("final_head")
    if not isinstance(baseline, str) or re.fullmatch(r"[a-f0-9]{40}", baseline) is None:
        findings.append("baseline_head is not a Git SHA")
    if not isinstance(final, str) or re.fullmatch(r"[a-f0-9]{40}", final) is None:
        findings.append("final_head is not a Git SHA")
    derived_head_changed = (
        isinstance(baseline, str)
        and isinstance(final, str)
        and baseline != final
    )
    if type(ledger.get("head_changed")) is bool and ledger["head_changed"] != derived_head_changed:
        findings.append("head_changed conflicts with baseline_head/final_head")

    computed = derived_head_changed or any(
        ledger.get(field) is True for field in _MUTATION_SIGNALS
    )
    if type(ledger.get("mutation_started")) is bool and ledger["mutation_started"] != computed:
        findings.append("mutation_started conflicts with trusted mutation signals")
    return computed, tuple(findings)


def mutation_from_ledger(ledger: Mapping[str, object]) -> bool:
    return audit_ledger(ledger)[0]


def trusted_route_metadata(
    ledger: Mapping[str, object], agent_claims: Mapping[str, object]
) -> dict[str, object]:
    """Return route/audit metadata only from the trusted ledger record."""

    del agent_claims
    return {field: ledger[field] for field in TRUSTED_LEDGER_FIELDS if field in ledger}


def _is_child(path: str, parent: str) -> bool:
    if not path or not parent:
        return False
    child_parts = PurePath(path).parts
    parent_parts = PurePath(parent).parts
    return len(child_parts) > len(parent_parts) and child_parts[: len(parent_parts)] == parent_parts


def evaluate_review(request: ReviewRequest) -> ReviewDecision:
    findings = list(request.findings)
    verified: list[str] = []
    unverified: list[str] = []
    evidence_conflict = False
    ledger = request.ledger

    if request.coder_stage != ReadinessStage.IMPLEMENTED_BY_CODER:
        findings.append("coder did not return implemented_by_coder")

    if not request.ci_green:
        findings.append("CI is not green")
    else:
        verified.append("CI passed; this is not review approval")

    missing_files = sorted(request.required_files - request.changed_files)
    if missing_files:
        findings.append("required files unchanged: " + ", ".join(missing_files))

    successful_checks = {
        check.name for check in request.integration_results if check.successful
    }
    missing_checks = sorted(set(request.required_integration_checks) - successful_checks)
    if request.protocol_changed and not request.required_integration_checks:
        findings.append("cross-component protocol change lacks required integration checks")
    if missing_checks:
        findings.append("trusted integration checks missing or unsuccessful: " + ", ".join(missing_checks))
    elif request.required_integration_checks:
        verified.append("required GitHub integration checks passed")

    if request.high_risk and not request.required_integration_checks:
        findings.append("high-risk acceptance lacks named trusted integration checks")

    if ledger is None:
        findings.append("trusted ledger evidence is missing")
    else:
        required_ledger = {
            "task_id",
            "run_id",
            "workspace_path",
            "workspace_source_ref",
            "baseline_head",
            "final_head",
            "mutation_started",
        } | set(_MUTATION_SIGNALS)
        missing_ledger = sorted(required_ledger - ledger.keys())
        if missing_ledger:
            findings.append("ledger evidence fields missing: " + ", ".join(missing_ledger))

        workspace_path = str(ledger.get("workspace_path", ""))
        if workspace_path != request.process_cwd:
            findings.append("ledger workspace_path differs from process cwd")
        elif workspace_path:
            verified.append("effective process cwd matches ledger workspace_path")

        if workspace_path in {"/workspace", "/workspace-base"} or _is_child(
            workspace_path, request.base_workspace
        ):
            findings.append("effective workspace resolves to shared/base checkout")

        computed_mutation, audit_findings = audit_ledger(ledger)
        findings.extend(audit_findings)
        ledger_mutation = ledger.get("mutation_started")
        if audit_findings or (
            ledger_mutation is False
            and (computed_mutation or request.github_mutation_observed)
        ):
            evidence_conflict = True
            if request.github_mutation_observed and ledger_mutation is False:
                findings.append("GitHub mutation conflicts with ledger mutation_started=false")
        elif ledger_mutation is True or computed_mutation:
            verified.append("mutation_started is supported by trusted evidence")

    if request.rollout_only_checks:
        unverified.extend(request.rollout_only_checks)

    if evidence_conflict:
        status = ReviewStatus.BLOCKED
        action = "audit workspace, Git ancestry and ledger before any further pipeline action"
        delegate_fix = False
    elif findings:
        status = ReviewStatus.CHANGES_REQUESTED
        if request.review_fix_iterations >= 2:
            action = "escalate to owner or independent executor; preserve the existing PR"
            delegate_fix = False
        else:
            action = "continue fixes in the existing PR"
            delegate_fix = True
    else:
        status = ReviewStatus.APPROVED
        action = "request explicit merge authorization; keep rollout checks open"
        delegate_fix = False

    stage = (
        ReadinessStage.REVIEW_APPROVED
        if status is ReviewStatus.APPROVED
        else ReadinessStage.REVIEW_CHANGES_REQUESTED
    )
    return ReviewDecision(
        status=status,
        stage=stage,
        verified_facts=tuple(verified),
        agent_claims_not_independently_verified=tuple(unverified),
        review_findings=tuple(findings),
        rollout_only_checks=request.rollout_only_checks,
        recommended_next_action=action,
        evidence_conflict=evidence_conflict,
        delegate_fix=delegate_fix,
    )
