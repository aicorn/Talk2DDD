"""PhaseEngine: finite-state machine driving DDD conversation phases."""

from __future__ import annotations

from typing import Optional

from app.agent.context import (
    AgentContext,
    Phase,
    PhaseTransition,
    PHASE_ORDER,
)


class PhaseEngine:
    """Evaluates and applies phase transitions for an AgentContext."""

    def evaluate(self, ctx: AgentContext, user_message: str) -> Optional[Phase]:
        """Check whether a phase transition should occur.

        Returns the target Phase if a transition is warranted, else None.
        Only explicit slash commands trigger a phase change — all other
        phase navigation is handled via the UI buttons (switch_phase).
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
        if "/techstack" in msg_lower:
            # "/techstack skip" — user explicitly skips tech stack selection
            if "skip" in msg_lower:
                ctx.tech_stack_preferences.skipped = True
                ctx.tech_stack_preferences.confirmed = True
                return None  # no phase change needed
            # "/techstack" alone — reset so AI re-collects preferences
            ctx.tech_stack_preferences.confirmed = False
            ctx.tech_stack_preferences.skipped = False
            # Jump to MODEL_DESIGN so the tech stack instructions are active
            return Phase.MODEL_DESIGN

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

    def get_adjacent_phase(self, ctx: AgentContext, direction: str) -> Optional[Phase]:
        """Return the phase adjacent to the current one in *direction*.

        Args:
            ctx: Current agent context.
            direction: ``"next"`` for the following phase, ``"back"`` for the previous.

        Returns:
            The target :class:`Phase`, or ``None`` if already at the boundary.

        Raises:
            ValueError: If *direction* is not ``"next"`` or ``"back"``.
        """
        if direction == "next":
            return self._next_phase(ctx)
        if direction == "back":
            return self._prev_phase(ctx)
        raise ValueError(f"Invalid direction '{direction}'. Must be 'next' or 'back'.")

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
