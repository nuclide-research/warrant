from __future__ import annotations
from datetime import datetime, timezone

from agent.plan import Plan
from .models import RunState, VerifierResult, CitationReport


def generate_citation_report(
    plan: Plan,
    run_state: RunState,
    verifier_results: dict[str, VerifierResult],
    suspiciously_clean_node_threshold: int = 5,
) -> CitationReport:
    grounded_clean = 0
    grounded_conflicted = 0
    grounded_ungrounded = 0
    judgment_calls_documented = 0
    judgment_calls_undocumented = 0

    for node in plan.nodes:
        if node.grounds_state == "clean":
            grounded_clean += 1
        elif node.grounds_state == "conflicted":
            grounded_conflicted += 1
        else:
            grounded_ungrounded += 1
            if node.id in verifier_results:
                judgment_calls_documented += 1
            else:
                judgment_calls_undocumented += 1

    tier1_run = 0
    tier1_failed_integrity = 0
    tier1_failed_audit = 0
    tier2_computed = 0
    tier3_assessed = 0

    for vr in verifier_results.values():
        for co in vr.check_outcomes:
            if co.tier == 1:
                tier1_run += 1
                if co.passed is False:
                    if co.provenance == "from_grounds":
                        tier1_failed_integrity += 1
                    else:
                        tier1_failed_audit += 1
            elif co.tier == 2:
                tier2_computed += 1
            elif co.tier == 3:
                tier3_assessed += 1

    plan_amendments = sum(1 for n in plan.nodes if n.amended_from is not None)

    suspiciously_clean = (
        judgment_calls_undocumented == 0
        and tier1_failed_integrity == 0
        and tier1_failed_audit == 0
        and plan_amendments == 0
        and len(plan.nodes) >= suspiciously_clean_node_threshold
    )

    node_verdicts: dict[str, str] = {}
    for node in plan.nodes:
        if node.id in verifier_results:
            node_verdicts[node.id] = verifier_results[node.id].verdict
        else:
            node_verdicts[node.id] = "unverified"

    return CitationReport(
        run_id=run_state.run_id,
        plan_id=plan.plan_id,
        grounded_clean=grounded_clean,
        grounded_conflicted=grounded_conflicted,
        grounded_ungrounded=grounded_ungrounded,
        judgment_calls_documented=judgment_calls_documented,
        judgment_calls_undocumented=judgment_calls_undocumented,
        tier1_run=tier1_run,
        tier1_failed_integrity=tier1_failed_integrity,
        tier1_failed_audit=tier1_failed_audit,
        tier2_computed=tier2_computed,
        tier3_assessed=tier3_assessed,
        plan_amendments=plan_amendments,
        suspiciously_clean=suspiciously_clean,
        node_verdicts=node_verdicts,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def render_citation_report(report: CitationReport) -> str:
    grounded_total = report.grounded_clean + report.grounded_conflicted
    jc_total = report.judgment_calls_documented + report.judgment_calls_undocumented
    undoc_flag = " <- flag" if report.judgment_calls_undocumented > 0 else ""
    failed_total = report.tier1_failed_integrity + report.tier1_failed_audit
    amendments_note = "  (see version diff)" if report.plan_amendments > 0 else ""

    lines = [
        f"grounded decisions:    {grounded_total:>4}   "
        f"(clean {report.grounded_clean}, conflicted {report.grounded_conflicted})",
        f"judgment calls:        {jc_total:>4}   "
        f"(documented {report.judgment_calls_documented}, "
        f"undocumented {report.judgment_calls_undocumented}{undoc_flag})",
        f"tier-1 checks:         {report.tier1_run:>4} run / {failed_total} failed",
        f"                            "
        f"({report.tier1_failed_integrity} from_grounds <- integrity, "
        f"{report.tier1_failed_audit} from_topic <- audit catch)",
        f"tier-2 metrics:        {report.tier2_computed:>4} computed",
        f"tier-3 principles:     {report.tier3_assessed:>4} assessed, judgment-only",
        f"plan amendments:       {report.plan_amendments:>4}{amendments_note}",
    ]
    if report.suspiciously_clean:
        lines.append("SUSPICIOUSLY CLEAN — review manually")
    return "\n".join(lines)
