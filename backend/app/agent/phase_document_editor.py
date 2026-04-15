"""PhaseDocumentEditor and OutOfScopeHandler for the phase-opening suggestion mechanism.

These classes are driven by the ``UserIntentClassifier`` result produced by
``AgentCore._classify_and_apply_intent()`` each conversation turn.

Design reference: §21.5 (PhaseDocumentEditor) and §21.9 (OutOfScopeHandler)
in docs/ai-agent-design.md.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.agent.context import (
    AgentContext,
    PhaseSuggestion,
    RefinementItem,
    SuggestionStatus,
    UserIntent,
)

_log = logging.getLogger(__name__)


class PhaseDocumentEditor:
    """Performs CRUD operations on ``PhaseSuggestion`` and ``domain_knowledge``
    based on the classified user intent.

    All write operations return a human-readable description of the change made
    (an empty string means "no change was applied").
    """

    # ------------------------------------------------------------------
    # Public CRUD interface
    # ------------------------------------------------------------------

    def apply_selection(
        self,
        ctx: AgentContext,
        target_index: int,
        selected_option: str,
        note: Optional[str] = None,
    ) -> str:
        """Write a user selection into a ``RefinementItem``.

        Idempotent: calling again with a different option overwrites the
        previous selection (UPDATE semantics, not append).

        Returns a human-readable description of the write, or empty string if
        the target item was not found.
        """
        suggestion = ctx.phase_suggestion
        if suggestion is None:
            return ""

        item = self._find_refinement_item(suggestion, target_index)
        if item is None:
            _log.warning(
                "apply_selection: index %d not found in suggestion for session %s",
                target_index,
                ctx.session_id,
            )
            return ""

        item.selected = selected_option
        if note:
            item.note = note
        self._update_suggestion_status(suggestion)

        msg = f"问题 {target_index}（{item.question[:30]}）：已选择「{selected_option}」"
        _log.info(
            "PhaseDocumentEditor.apply_selection: index=%d option=%r session=%s",
            target_index,
            selected_option,
            ctx.session_id,
        )
        return msg

    def add_refinement_items(
        self,
        ctx: AgentContext,
        target_index: int,
        new_items: List[RefinementItem],
    ) -> int:
        """Append new ``RefinementItem``s under the scenario that owns
        *target_index*.  Newly appended items get auto-incremented indices.

        Returns the number of items actually appended.
        """
        suggestion = ctx.phase_suggestion
        if suggestion is None or not new_items:
            return 0

        # Find the scenario refinement that contains target_index
        for sr in suggestion.scenario_refinements:
            if any(item.index == target_index for item in sr.items):
                max_idx = max((i.index for i in sr.items), default=0)
                for offset, item in enumerate(new_items, start=1):
                    item.index = max_idx + offset
                sr.items.extend(new_items)
                _log.info(
                    "PhaseDocumentEditor.add_refinement_items: added %d items "
                    "under index=%d session=%s",
                    len(new_items),
                    target_index,
                    ctx.session_id,
                )
                return len(new_items)

        _log.warning(
            "add_refinement_items: index %d not found in suggestion for session %s",
            target_index,
            ctx.session_id,
        )
        return 0

    def dismiss_item(
        self,
        ctx: AgentContext,
        target_index: int,
        reason: Optional[str] = None,
    ) -> str:
        """Mark a suggestion item as dismissed (user explicitly rejected it).

        Returns a human-readable description of the change, or empty string if
        the target item was not found.
        """
        suggestion = ctx.phase_suggestion
        if suggestion is None:
            return ""

        item = self._find_refinement_item(suggestion, target_index)
        if item is None:
            _log.warning(
                "dismiss_item: index %d not found in suggestion for session %s",
                target_index,
                ctx.session_id,
            )
            return ""

        item.dismissed = True
        if reason:
            item.note = reason
        self._update_suggestion_status(suggestion)

        msg = f"问题 {target_index}（{item.question[:30]}）：已跳过"
        _log.info(
            "PhaseDocumentEditor.dismiss_item: index=%d session=%s",
            target_index,
            ctx.session_id,
        )
        return msg

    def update_document_field(
        self,
        ctx: AgentContext,
        field_path: str,
        new_value: Any,
    ) -> bool:
        """Generic field update via a dot-separated path into ``domain_knowledge``.

        Returns ``True`` on success, ``False`` if the path is invalid.
        """
        parts = field_path.split(".")
        try:
            obj: Any = ctx.domain_knowledge
            for part in parts[:-1]:
                obj = getattr(obj, part)
            setattr(obj, parts[-1], new_value)
            _log.info(
                "PhaseDocumentEditor.update_document_field: path=%r session=%s",
                field_path,
                ctx.session_id,
            )
            return True
        except (AttributeError, TypeError) as exc:
            _log.warning(
                "PhaseDocumentEditor.update_document_field failed for path=%r: %s",
                field_path,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_refinement_item(
        suggestion: PhaseSuggestion, index: int
    ) -> Optional[RefinementItem]:
        """Search all scenario refinements for an item with the given 1-based index."""
        for sr in suggestion.scenario_refinements:
            for item in sr.items:
                if item.index == index:
                    return item
        return None

    @staticmethod
    def _update_suggestion_status(suggestion: PhaseSuggestion) -> None:
        """Recalculate and update the top-level ``SuggestionStatus``."""
        all_items: List[RefinementItem] = []
        for sr in suggestion.scenario_refinements:
            all_items.extend(sr.items)
        if not all_items:
            return

        resolved = sum(
            1 for i in all_items if i.selected is not None or i.dismissed
        )
        if resolved == 0:
            suggestion.status = SuggestionStatus.PENDING
        elif resolved == len(all_items):
            suggestion.status = SuggestionStatus.COMPLETED
        else:
            suggestion.status = SuggestionStatus.PARTIAL


class OutOfScopeHandler:
    """Generates a context-aware friendly reminder when ``UserIntent.OUT_OF_SCOPE``
    is detected.

    The reminder text is injected into the conversational AI's system prompt so
    the AI can present it naturally to the user.  It lists the actions that are
    still meaningful given the current ``PhaseSuggestion`` state.

    Design reference: §21.9 of ai-agent-design.md.
    """

    def build_reminder(
        self,
        ctx: AgentContext,
        out_of_scope_hint: Optional[str] = None,
    ) -> str:
        """Return a system-prompt instruction describing available actions.

        The returned text:
        1. Names the count of pending items (if any).
        2. Lists the operations the user can perform right now.
        3. Gently guides the user to complete the current-phase suggestion.
        """
        suggestion = ctx.phase_suggestion

        # Collect pending item indices
        pending_indices: List[int] = []
        if suggestion is not None:
            for sr in suggestion.scenario_refinements:
                for item in sr.items:
                    if item.selected is None and not item.dismissed:
                        pending_indices.append(item.index)

        has_pending = bool(pending_indices)
        hint_text = (
            f"\n（用户似乎在问：{out_of_scope_hint}）" if out_of_scope_hint else ""
        )

        # Build a list of currently meaningful actions
        actions: List[str] = []
        if has_pending:
            example_idx = pending_indices[0]
            actions.append(
                f"① 对建议中的某个问题做出选择，例如：\n"
                f'   "第 {example_idx} 条，选 [某备选方案]"'
            )
        actions.append(
            "② 要求生成更多细化问题，例如：\n"
            '   "还有其他需要细化的问题吗？"'
        )
        actions.append(
            "③ 要求对某条问题进一步说明，例如：\n"
            '   "问题 X，能详细说明两种方案的区别吗？"'
        )
        if has_pending:
            actions.append(
                "④ 跳过某条不需要的建议，例如：\n"
                '   "第 X 条不需要了"'
            )
        actions.append(
            "⑤ 直接补充你的想法，例如：\n"
            '   "我希望支持多图封面"'
        )

        actions_text = "\n\n".join(actions)

        if has_pending:
            indices_str = "、".join(str(i) for i in pending_indices[:5])
            pending_note = (
                f"\n\n当前还有 {len(pending_indices)} 个问题待确认"
                f"（第 {indices_str} 条）。\n"
                "请先完成本阶段建议的确认，再继续其他操作。"
            )
        else:
            pending_note = (
                "\n\n当前所有建议条目已处理完毕，可以继续下一步操作。"
            )

        return (
            "[系统提示] 用户的请求超出了当前阶段建议体系的处理范围。"
            + hint_text
            + "\n请友好地告知用户，在当前阶段，你可以帮助他们：\n\n"
            + actions_text
            + pending_note
        )
