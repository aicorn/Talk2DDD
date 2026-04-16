"""KnowledgeExtractor: parses structured XML tags from AI replies."""

from __future__ import annotations

import logging
import re
from typing import List, Optional
from xml.etree import ElementTree as ET

from app.agent.context import (
    AgentContext,
    BusinessScenario,
    ChangeType,
    ClarificationQuestion,
    ConceptType,
    DomainConcept,
    RequirementChange,
    ScenarioStatus,
    TechChoice,
    TechProficiency,
)

_log = logging.getLogger(__name__)


def _extract_raw_tags(text: str, tag: str) -> List[str]:
    """Return all substrings matching ``<tag ...>...</tag>`` in *text*."""
    pattern = rf"<{tag}(?:\s[^>]*)?>.*?</{tag}>"
    return re.findall(pattern, text, re.DOTALL | re.IGNORECASE)


def _safe_parse_xml(xml_str: str) -> Optional[ET.Element]:
    """Parse an XML fragment, returning None on any parse error."""
    try:
        return ET.fromstring(xml_str)
    except ET.ParseError:
        return None


class KnowledgeExtractor:
    """Extracts structured knowledge from an AI reply and merges it into ctx."""

    def extract(self, ai_reply: str, ctx: AgentContext) -> None:
        """Parse *ai_reply* and merge extracted knowledge into *ctx* in-place."""
        self._extract_project_info(ai_reply, ctx)
        self._extract_concepts(ai_reply, ctx)
        self._extract_scenarios(ai_reply, ctx)
        self._extract_clarifications(ai_reply, ctx)
        self._extract_requirement_changes(ai_reply, ctx)
        self._extract_tech_stack(ai_reply, ctx)

    # ------------------------------------------------------------------
    # Private extraction helpers
    # ------------------------------------------------------------------

    def _extract_project_info(self, text: str, ctx: AgentContext) -> None:
        pattern = r"<project_info\s+([^/]+)/>"
        for match in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
            attrs_str = match.group(1)
            name_m = re.search(r'name=["\']([^"\']+)["\']', attrs_str)
            domain_m = re.search(r'domain=["\']([^"\']+)["\']', attrs_str)
            if name_m and not ctx.domain_knowledge.project_name:
                ctx.domain_knowledge.project_name = name_m.group(1).strip()
            if domain_m and not ctx.domain_knowledge.domain_description:
                ctx.domain_knowledge.domain_description = domain_m.group(1).strip()

    def _extract_concepts(self, text: str, ctx: AgentContext) -> None:
        for raw in _extract_raw_tags(text, "concept"):
            elem = _safe_parse_xml(raw)
            if elem is None:
                # XML parse failed — attempt regex fallback to salvage name/type/text
                _log.debug(
                    "XML parse failed for <concept> tag; trying regex fallback. "
                    "raw (truncated): %.120s",
                    raw,
                )
                name_m = re.search(r'name=["\']([^"\']+)["\']', raw, re.IGNORECASE)
                if not name_m:
                    continue
                type_m = re.search(r'type=["\']([^"\']+)["\']', raw, re.IGNORECASE)
                conf_m = re.search(r'confidence=["\']([^"\']+)["\']', raw, re.IGNORECASE)
                text_m = re.search(
                    r"<concept[^>]*>(.*?)</concept>", raw, re.DOTALL | re.IGNORECASE
                )
                name = name_m.group(1).strip()
                type_str = type_m.group(1).strip().upper() if type_m else "ENTITY"
                confidence_str = conf_m.group(1).strip() if conf_m else "0.8"
                description = text_m.group(1).strip() if text_m else ""
            else:
                name = (elem.get("name") or "").strip()
                type_str = (elem.get("type") or "ENTITY").upper()
                confidence_str = elem.get("confidence") or "0.8"
                description = (elem.text or "").strip()

            if not name:
                continue
            try:
                concept_type = ConceptType(type_str)
            except ValueError:
                concept_type = ConceptType.ENTITY
            try:
                confidence = float(confidence_str)
            except ValueError:
                confidence = 0.8

            existing = next(
                (
                    c
                    for c in ctx.domain_knowledge.domain_concepts
                    if c.name == name
                ),
                None,
            )
            if existing:
                existing.confidence = max(existing.confidence, confidence)
                if description:
                    existing.description = description
            else:
                ctx.domain_knowledge.domain_concepts.append(
                    DomainConcept(
                        name=name,
                        concept_type=concept_type,
                        description=description,
                        confidence=confidence,
                    )
                )
                _log.debug(
                    "Extracted new concept: name=%s type=%s (session=%s)",
                    name,
                    concept_type.value,
                    ctx.session_id,
                )

    def _extract_scenarios(self, text: str, ctx: AgentContext) -> None:
        for raw in _extract_raw_tags(text, "scenario"):
            elem = _safe_parse_xml(raw)
            if elem is None:
                # XML parse failed — attempt regex fallback to salvage id/name/text
                _log.debug(
                    "XML parse failed for <scenario> tag; trying regex fallback. "
                    "raw (truncated): %.120s",
                    raw,
                )
                # id is optional — use `*` so an empty id="" still matches and
                # falls through to the auto-generation logic below.
                id_m = re.search(r'id=["\']([^"\']*)["\']', raw, re.IGNORECASE)
                name_m = re.search(r'name=["\']([^"\']+)["\']', raw, re.IGNORECASE)
                if not name_m:
                    continue
                text_m = re.search(
                    r"<scenario[^>]*>(.*?)</scenario>", raw, re.DOTALL | re.IGNORECASE
                )
                scenario_id = id_m.group(1).strip() if id_m else ""
                name = name_m.group(1).strip()
                description = text_m.group(1).strip() if text_m else ""
            else:
                scenario_id = (elem.get("id") or "").strip()
                name = (elem.get("name") or "").strip()
                description = (elem.text or "").strip()

            if not name:
                continue

            existing = next(
                (
                    s
                    for s in ctx.domain_knowledge.business_scenarios
                    if s.name == name
                ),
                None,
            )
            if existing:
                if description:
                    existing.description = description
            else:
                auto_id = (
                    scenario_id
                    if scenario_id
                    else f"S{len(ctx.domain_knowledge.business_scenarios) + 1:03d}"
                )
                ctx.domain_knowledge.business_scenarios.append(
                    BusinessScenario(
                        id=auto_id,
                        name=name,
                        description=description,
                    )
                )
                _log.debug(
                    "Extracted new scenario via XML: id=%s name=%s (session=%s)",
                    auto_id,
                    name,
                    ctx.session_id,
                )

    def _extract_clarifications(self, text: str, ctx: AgentContext) -> None:
        for raw in _extract_raw_tags(text, "clarification"):
            elem = _safe_parse_xml(raw)
            if elem is None:
                continue
            q_id = (elem.get("id") or "").strip()
            answered = (elem.get("answered") or "false").lower() == "true"
            question = (elem.text or "").strip()

            # If answered="true", mark the matching question as resolved
            if answered:
                # Look up by ID first, then fall back to question text
                match = None
                if q_id:
                    match = next(
                        (q for q in ctx.clarification_queue if q.id == q_id), None
                    )
                if match is None and question:
                    match = next(
                        (q for q in ctx.clarification_queue if q.question == question),
                        None,
                    )
                if match:
                    match.answered = True
                continue

            # New question — skip if no text or already present (by ID or text)
            if not question:
                continue
            if q_id and any(q.id == q_id for q in ctx.clarification_queue):
                continue
            if any(q.question == question for q in ctx.clarification_queue):
                continue
            auto_id = (
                q_id if q_id else f"Q{len(ctx.clarification_queue) + 1:03d}"
            )
            ctx.clarification_queue.append(
                ClarificationQuestion(id=auto_id, question=question)
            )

    def merge_project_info_from_json(self, json_text: str, ctx: AgentContext) -> bool:
        """Parse a JSON object with project_name/domain_description and merge into *ctx*.

        This method is called after the dedicated project-info extraction AI call
        in Phase 1 (ICEBREAK) to reconcile any project information that was
        discussed but not captured via ``<project_info>`` XML tags.

        Only fills fields that are still empty in the context — consistent with
        the behaviour of ``_extract_project_info()``.

        Returns True if at least one field was updated, False otherwise.
        """
        import json as _json

        start = json_text.find("{")
        end = json_text.rfind("}")
        if start == -1 or end == -1 or end < start:
            return False

        try:
            data = _json.loads(json_text[start : end + 1])
        except (_json.JSONDecodeError, ValueError):
            return False

        if not isinstance(data, dict):
            return False

        updated = False
        project_name = (data.get("project_name") or "").strip()
        domain_description = (data.get("domain_description") or "").strip()

        if project_name and not ctx.domain_knowledge.project_name:
            ctx.domain_knowledge.project_name = project_name
            updated = True
        if domain_description and not ctx.domain_knowledge.domain_description:
            ctx.domain_knowledge.domain_description = domain_description
            updated = True

        return updated

    def merge_concepts_from_json(self, json_text: str, ctx: AgentContext) -> int:
        """Parse a JSON array of domain concepts and merge them into *ctx* in-place.

        This method is called after the dedicated concept-extraction AI call in
        Phase 3 (both on initial entry and after each conversation turn) to
        reconcile any concepts that were discussed but not captured via
        ``<concept>`` XML tags.

        Returns the number of new concepts added to the context.
        """
        import json as _json

        start = json_text.find("[")
        end = json_text.rfind("]")
        if start == -1 or end == -1 or end < start:
            return 0

        try:
            concepts_data = _json.loads(json_text[start : end + 1])
        except (_json.JSONDecodeError, ValueError):
            return 0

        if not isinstance(concepts_data, list):
            return 0

        added = 0
        for item in concepts_data:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or "").strip()
            if not name:
                continue
            type_str = (item.get("type") or "ENTITY").upper()
            description = (item.get("description") or "").strip()
            confidence_raw = item.get("confidence")
            try:
                confidence = float(confidence_raw) if confidence_raw is not None else 0.8
            except (ValueError, TypeError):
                confidence = 0.8
            try:
                concept_type = ConceptType(type_str)
            except ValueError:
                concept_type = ConceptType.ENTITY

            existing = next(
                (c for c in ctx.domain_knowledge.domain_concepts if c.name == name),
                None,
            )
            if existing:
                existing.confidence = max(existing.confidence, confidence)
                if description and not existing.description:
                    existing.description = description
            else:
                ctx.domain_knowledge.domain_concepts.append(
                    DomainConcept(
                        name=name,
                        concept_type=concept_type,
                        description=description,
                        confidence=confidence,
                    )
                )
                added += 1

        return added

    def merge_scenarios_from_json(self, json_text: str, ctx: AgentContext) -> int:
        """Parse a JSON array of scenarios and merge them into *ctx* in-place.

        This method is called after the dedicated scenario-extraction AI call
        in Phase 2 to reconcile any scenarios that were discussed in the
        conversation but not captured via ``<scenario>`` XML tags.

        Returns the number of new scenarios added to the context.
        """
        import json as _json

        # Tolerantly extract the outermost JSON array from the text by finding
        # the first '[' and the last ']'.  This is more robust than a regex
        # for arrays containing nested objects or brackets.
        start = json_text.find("[")
        end = json_text.rfind("]")
        if start == -1 or end == -1 or end < start:
            return 0

        try:
            scenarios_data = _json.loads(json_text[start : end + 1])
        except (_json.JSONDecodeError, ValueError):
            return 0

        if not isinstance(scenarios_data, list):
            return 0

        added = 0
        for item in scenarios_data:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or "").strip()
            if not name:
                continue
            description = (item.get("description") or "").strip()
            scenario_id = (item.get("id") or "").strip()

            existing = next(
                (s for s in ctx.domain_knowledge.business_scenarios if s.name == name),
                None,
            )
            if existing:
                # Supplement an empty description, but do not overwrite
                if description and not existing.description:
                    existing.description = description
            else:
                # Resolve any id collision before inserting
                def _next_id() -> str:
                    return f"S{len(ctx.domain_knowledge.business_scenarios) + 1:03d}"

                if scenario_id and any(
                    s.id == scenario_id
                    for s in ctx.domain_knowledge.business_scenarios
                ):
                    scenario_id = _next_id()
                auto_id = scenario_id if scenario_id else _next_id()
                ctx.domain_knowledge.business_scenarios.append(
                    BusinessScenario(id=auto_id, name=name, description=description)
                )
                added += 1

        return added

    def _extract_requirement_changes(self, text: str, ctx: AgentContext) -> None:
        for raw in _extract_raw_tags(text, "requirement_change"):
            elem = _safe_parse_xml(raw)
            if elem is None:
                continue
            change_type_str = (elem.get("type") or "ADD").upper()
            target_id = (elem.get("target_id") or "").strip() or None
            trigger_rollback = (
                (elem.get("trigger_rollback") or "false").lower() == "true"
            )

            desc_elem = elem.find("description")
            description = (
                (desc_elem.text or "").strip() if desc_elem is not None else ""
            )

            affected_elem = elem.find("affected_documents")
            affected_str = (
                (affected_elem.text or "").strip()
                if affected_elem is not None
                else ""
            )
            affected_docs = [
                d.strip() for d in affected_str.split(",") if d.strip()
            ]

            try:
                change_type = ChangeType(change_type_str)
            except ValueError:
                change_type = ChangeType.ADD

            change = RequirementChange(
                change_type=change_type,
                target_id=target_id,
                description=description,
                affected_documents=affected_docs,
            )
            ctx.requirement_changes.append(change)

            # Mark affected documents as stale
            if affected_docs:
                ctx.mark_documents_stale(affected_docs)

            # Update scenario status if MODIFY or DEPRECATE
            if target_id:
                scenario = next(
                    (
                        s
                        for s in ctx.domain_knowledge.business_scenarios
                        if s.id == target_id
                    ),
                    None,
                )
                if scenario:
                    if change_type == ChangeType.MODIFY:
                        scenario.status = ScenarioStatus.MODIFIED
                        scenario.version += 1
                    elif change_type == ChangeType.DEPRECATE:
                        scenario.status = ScenarioStatus.DEPRECATED

            # Signal rollback via phase_before_change (handled by PhaseEngine)
            if trigger_rollback and ctx.current_phase.value not in {
                "ICEBREAK",
                "REQUIREMENT",
            }:
                ctx.phase_before_change = ctx.current_phase

    def _extract_tech_stack(self, text: str, ctx: AgentContext) -> None:
        """Parse <tech_stack> tags and update ctx.tech_stack_preferences in-place."""
        for raw in _extract_raw_tags(text, "tech_stack"):
            elem = _safe_parse_xml(raw)
            if elem is None:
                continue
            skipped_str = (elem.get("skipped") or "false").lower()
            skipped = skipped_str == "true"
            if skipped:
                ctx.tech_stack_preferences.skipped = True
                ctx.tech_stack_preferences.confirmed = True
                return

            _VALID_CATEGORIES = {
                "frontend", "backend", "database",
                "infrastructure", "messaging", "custom",
            }
            for tech_elem in elem.findall("tech"):
                name = (tech_elem.get("name") or "").strip()
                if not name:
                    continue
                category = (tech_elem.get("category") or "custom").lower().strip()
                if category not in _VALID_CATEGORIES:
                    category = "custom"
                version = (tech_elem.get("version") or "").strip() or None
                reason = (tech_elem.text or "").strip() or None
                proficiency_str = (
                    tech_elem.get("proficiency") or "FAMILIAR"
                ).upper()
                try:
                    proficiency = TechProficiency(proficiency_str)
                except ValueError:
                    proficiency = TechProficiency.FAMILIAR

                target_list: list = getattr(
                    ctx.tech_stack_preferences, category
                )
                existing = next(
                    (c for c in target_list if c.name.lower() == name.lower()),
                    None,
                )
                if existing:
                    if version:
                        existing.version = version
                    if reason:
                        existing.reason = reason
                    existing.proficiency = proficiency
                else:
                    target_list.append(
                        TechChoice(
                            name=name,
                            category=category,
                            version=version,
                            reason=reason,
                            proficiency=proficiency,
                        )
                    )

            ctx.tech_stack_preferences.confirmed = True
