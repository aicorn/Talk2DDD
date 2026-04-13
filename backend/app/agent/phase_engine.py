"""PhaseEngine: finite-state machine driving DDD conversation phases."""

from __future__ import annotations

from typing import Optional

from app.agent.context import (
    AgentContext,
    Phase,
    PhaseTransition,
    PHASE_ORDER,
)

# Exit-condition lambdas for each phase
_EXIT_CONDITIONS = {
    Phase.ICEBREAK: lambda ctx: bool(
        ctx.domain_knowledge.project_name and ctx.domain_knowledge.domain_description
    ),
    Phase.REQUIREMENT: lambda ctx: len(
        [
            s
            for s in ctx.domain_knowledge.business_scenarios
            if s.status.value != "DEPRECATED"
        ]
    )
    >= 3,
    Phase.DOMAIN_EXPLORE: lambda ctx: len(ctx.domain_knowledge.domain_concepts) >= 5,
    Phase.MODEL_DESIGN: lambda ctx: len(ctx.domain_knowledge.bounded_contexts) >= 1,
    Phase.DOC_GENERATE: lambda ctx: any(
        d.status.value == "CURRENT" for d in ctx.generated_documents
    ),
    Phase.REVIEW_REFINE: lambda ctx: False,  # only manual completion
}

# Phases where requirement-change rollback is allowed
_ROLLBACK_ENABLED_PHASES = {
    Phase.DOMAIN_EXPLORE,
    Phase.MODEL_DESIGN,
    Phase.DOC_GENERATE,
    Phase.REVIEW_REFINE,
}

# Chinese keywords that signal a requirement change
_CHANGE_SIGNALS = [
    "还有一个需求",
    "另外",
    "补充一点",
    "之前说的",
    "其实",
    "改一下",
    "调整一下",
    "变成了",
    "取消",
    "砍掉",
    "不需要了",
    "去掉",
    "/change",
]


class PhaseEngine:
    """Evaluates and applies phase transitions for an AgentContext."""

    def evaluate(self, ctx: AgentContext, user_message: str) -> Optional[Phase]:
        """Check whether a phase transition should occur.

        Returns the target Phase if a transition is warranted, else None.
        Side-effect: sets ctx.phase_before_change on rollback.
        """
        msg_lower = user_message.lower()

        # Explicit navigation commands take precedence
        if "/next" in msg_lower:
            return self._next_phase(ctx)
        if "/back" in msg_lower:
            return self._prev_phase(ctx)
        if "/generate" in msg_lower:
            return Phase.DOC_GENERATE
        if "/model" in msg_lower:
            return Phase.MODEL_DESIGN

        # Automatic exit-condition check
        if _EXIT_CONDITIONS[ctx.current_phase](ctx):
            return self._next_phase(ctx)

        # Requirement-change rollback (P3–P6 only)
        if ctx.current_phase in _ROLLBACK_ENABLED_PHASES:
            if any(signal in user_message for signal in _CHANGE_SIGNALS):
                ctx.phase_before_change = ctx.current_phase
                return Phase.REQUIREMENT

        return None

    def advance_phase(
        self, ctx: AgentContext, to_phase: Phase, reason: str = ""
    ) -> None:
        """Apply a phase transition to *ctx* in-place."""
        transition = PhaseTransition(
            from_phase=ctx.current_phase,
            to_phase=to_phase,
            reason=reason,
        )
        ctx.phase_history.append(transition)
        ctx.current_phase = to_phase

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _next_phase(self, ctx: AgentContext) -> Optional[Phase]:
        try:
            idx = PHASE_ORDER.index(ctx.current_phase)
            if idx < len(PHASE_ORDER) - 1:
                return PHASE_ORDER[idx + 1]
        except ValueError:
            pass
        return None

    def _prev_phase(self, ctx: AgentContext) -> Optional[Phase]:
        try:
            idx = PHASE_ORDER.index(ctx.current_phase)
            if idx > 0:
                return PHASE_ORDER[idx - 1]
        except ValueError:
            pass
        return None
