"""
Context Resolver module for HTH2.0.
Resolves conversational follow-up queries using previous structured query state in conversation.json,
and builds compact context objects for LLM consumption.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from analyst.models import QuerySpec, ConditionSpec, FilterSpec, SortSpec

logger = logging.getLogger(__name__)


class ContextResolver:
    """
    Analyzes user queries against chat history in conversation.json
    to inherit previous intent, operation, filters, condition patterns, and file references.
    """

    def resolve_context(
        self,
        chat_id: str,
        current_query: str,
        messages: List[Dict[str, Any]],
        files: List[Dict[str, Any]]
    ) -> Tuple[Optional[QuerySpec], Dict[str, Any], Optional[str]]:
        """
        Resolves follow-up queries.
        Returns:
            (resolved_query_spec, compact_llm_context, selected_file_id)
        """
        clean_q = current_query.strip()
        q_lower = clean_q.lower()

        # 1. Find the most recent assistant message with analytical query state
        prev_assistant_msg = self._find_last_analytical_message(messages)

        # 2. Determine target file_id for this chat
        selected_file_id = self._resolve_file_id(clean_q, files, prev_assistant_msg)

        if not prev_assistant_msg:
            compact_context = {
                "chat_id": chat_id,
                "available_files": [{"file_id": f.get("file_id"), "filename": f.get("filename")} for f in files],
                "previous_query": None,
                "previous_result": None,
                "current_user_query": clean_q
            }
            return None, compact_context, selected_file_id

        prev_spec_dict = prev_assistant_msg.get("query_spec") or {}
        prev_intent = prev_assistant_msg.get("intent") or {}
        prev_result = prev_assistant_msg.get("result") or {}

        # Build clean active analytical state (Requirement STEP 9)
        active_query = None
        if prev_spec_dict:
            active_query = {
                "operation": prev_spec_dict.get("operation", "sum"),
                "metric": prev_spec_dict.get("column"),
                "column": prev_spec_dict.get("column"),
                "columns": prev_spec_dict.get("columns", []),
                "aggregation": prev_spec_dict.get("operation", "sum"),
                "filters": [
                    f.to_dict() if hasattr(f, "to_dict") else f
                    for f in (prev_spec_dict.get("filters") or [])
                ],
                "group_by": prev_spec_dict.get("group_by", [])
            }
        elif prev_intent:
            active_query = prev_intent

        # Build compact context for LLM (Requirement 7 & STEP 9)
        compact_context = {
            "chat_id": chat_id,
            "available_files": [{"file_id": f.get("file_id"), "filename": f.get("filename")} for f in files],
            "previous_query": active_query,
            "previous_result": prev_result,
            "current_user_query": clean_q
        }

        # 3. Check for Follow-Up Intent Patterns
        is_follow_up, new_param_type, new_val = self._detect_follow_up_intent(q_lower, prev_intent or prev_spec_dict)

        if not is_follow_up:
            return None, compact_context, selected_file_id

        logger.info(f"ContextResolver: Resolved follow-up query '{clean_q}'. Parameter '{new_param_type}' updated to '{new_val}'")

        # 4. Construct Resolved QuerySpec by inheriting previous query state
        resolved_spec = self._inherit_and_update_query_spec(
            prev_spec_dict=prev_spec_dict,
            param_type=new_param_type,
            new_val=new_val,
            raw_question=clean_q,
            file_id=selected_file_id
        )

        return resolved_spec, compact_context, selected_file_id

    def _find_last_analytical_message(self, messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        for msg in reversed(messages):
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
            if role == "assistant":
                q_spec = msg.get("query_spec") if isinstance(msg, dict) else getattr(msg, "query_spec", None)
                intent = msg.get("intent") if isinstance(msg, dict) else getattr(msg, "intent", None)
                result = msg.get("result_json") or msg.get("result") if isinstance(msg, dict) else getattr(msg, "result_json", None)
                if q_spec or intent or result:
                    return {
                        "query_spec": q_spec,
                        "intent": intent,
                        "result": result
                    }
        return None

    def _resolve_file_id(
        self,
        query: str,
        files: List[Dict[str, Any]],
        prev_msg: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        if not files:
            return None
        if len(files) == 1:
            return files[0].get("file_id")

        q_lower = query.lower()
        # Explicit file name mention
        for f in files:
            fname = (f.get("filename") or "").lower()
            if fname and (fname in q_lower or fname.split(".")[0] in q_lower):
                return f.get("file_id")

        # Inherit file_id from previous message
        if prev_msg:
            prev_spec = prev_msg.get("query_spec") or {}
            if prev_spec.get("file_id"):
                return prev_spec.get("file_id")

        # Column matching across files schemas
        for f in files:
            cols = [c.lower() for c in (f.get("schema", {}).get("columns", []))]
            if any(c in q_lower for c in cols if len(c) > 2):
                return f.get("file_id")

        # Fallback to latest file
        return files[-1].get("file_id")

    def _detect_follow_up_intent(
        self,
        q_lower: str,
        prev_query_data: Dict[str, Any]
    ) -> Tuple[bool, str, Any]:
        """
        Detects follow-up phrases (e.g. 'similarly for B grade', 'same for B', 'what about A+')
        and extracts the changed parameter value.
        """
        follow_up_triggers = [
            r"\bsimilarly\b",
            r"\bsame\b",
            r"\bdo\s+it\b",
            r"\bdo\s+the\s+same\b",
            r"\bplot\s+the\s+same\b",
            r"\bwhat\s+about\b",
            r"\bhow\s+about\b",
            r"\bcompare\s+(?:this\s+)?with\b",
            r"\bcompare\b",
            r"\bnow\s+(?:for|calculate|show|get|filter)\b",
            r"\balso\s+for\b",
            r"\bonly\b"
        ]

        has_trigger = any(re.search(t, q_lower) for t in follow_up_triggers)

        # Multi-grade comparison pattern: e.g. "show only A and B", "compare O and A+", "only A and B"
        multi_match = re.search(
            r"(?:show\s+only|compare|only|show)\s+([A-Za-z0-9\+\*\-]+)\s+and\s+([A-Za-z0-9\+\*\-]+)(?:\s+grades?)?",
            q_lower
        )
        if multi_match:
            v1 = multi_match.group(1).strip().upper()
            v2 = multi_match.group(2).strip().upper()
            ignored_words = {"IT", "THE", "SAME", "FOR", "THIS", "WITH", "CALCULATE", "SHOW", "PLOT", "AGAIN", "ANOTHER", "EACH", "ALL"}
            if v1 not in ignored_words and v2 not in ignored_words:
                return True, "condition_values", [v1, v2]

        # Grade value extraction e.g. "only B grade", "only B", "for B grade", "for B", "grade B", "what about O", "what about O?"
        grade_patterns = [
            r"\bonly\s+([A-Za-z0-9\+\*\-]+)(?:\s+grade)?\b",
            r"(?:for|with|about|show|calculate)?\s*([A-Za-z0-9\+\*\-]+)\s+grade\b",
            r"grade\s+([A-Za-z0-9\+\*\-]+)\b",
            r"(?:what\s+about|how\s+about)\s+([A-Za-z0-9\+\*\-]+)\??\b",
            r"(?:similarly|same|do it|compare with|now for|also for)\s+(?:for\s+)?([A-Za-z0-9\+\*\-]+)\b"
        ]

        extracted_val = None
        for pattern in grade_patterns:
            match = re.search(pattern, q_lower)
            if match:
                val = match.group(1).strip().upper()
                ignored_words = {"IT", "THE", "SAME", "FOR", "THIS", "WITH", "CALCULATE", "SHOW", "PLOT", "AGAIN", "ANOTHER", "EACH", "ALL"}
                if val not in ignored_words:
                    extracted_val = val
                    break

        if extracted_val:
            return True, "condition_value", extracted_val

        if has_trigger:
            m = re.search(r"(?:similarly|same|do it|what about|how about|now|only)\s+(?:for\s+)?([a-zA-Z0-9_\s]+)", q_lower)
            if m:
                v = m.group(1).strip().upper()
                return True, "condition_value", v

        return False, "", None

    def _inherit_and_update_query_spec(
        self,
        prev_spec_dict: Dict[str, Any],
        param_type: str,
        new_val: Any,
        raw_question: str,
        file_id: Optional[str]
    ) -> QuerySpec:

        prev_op = prev_spec_dict.get("operation", "conditional_count")
        col = prev_spec_dict.get("column")
        cols = prev_spec_dict.get("columns") or []
        group_by = prev_spec_dict.get("group_by") or []

        # Determine operation and condition when inheriting
        if param_type == "condition_values":
            # Multiple values -> multi_column_value_distribution with subset filter
            op = "multi_column_value_distribution"
            cond_spec = ConditionSpec(operator="in", value=new_val)
        elif param_type == "condition_value":
            # Single value -> conditional_count
            op = "conditional_count"
            cond_spec = ConditionSpec(operator="equals", value=new_val)
        else:
            op = prev_op
            prev_cond = prev_spec_dict.get("condition") or {}
            cond_op = "equals"
            if isinstance(prev_cond, dict):
                cond_op = prev_cond.get("operator", "equals")
            elif hasattr(prev_cond, "operator"):
                cond_op = getattr(prev_cond, "operator", "equals")
            cond_spec = ConditionSpec(operator=cond_op, value=new_val) if prev_cond else None

        filters = []
        for f in prev_spec_dict.get("filters") or []:
            if isinstance(f, dict):
                filters.append(FilterSpec(column=f["column"], operator=f.get("operator", "="), value=f.get("value")))
            elif hasattr(f, "column"):
                filters.append(FilterSpec(column=f.column, operator=getattr(f, "operator", "="), value=getattr(f, "value", None)))

        sort = []
        for s in prev_spec_dict.get("sort") or []:
            if isinstance(s, dict):
                sort.append(SortSpec(column=s["column"], direction=s.get("direction", "desc")))
            elif hasattr(s, "column"):
                sort.append(SortSpec(column=s.column, direction=getattr(s, "direction", "desc")))

        limit = prev_spec_dict.get("limit")

        return QuerySpec(
            operation=op,
            column=col,
            columns=cols,
            condition=cond_spec,
            group_by=group_by,
            filters=filters,
            sort=sort,
            limit=limit,
            raw_question=raw_question,
            file_id=file_id or prev_spec_dict.get("file_id")
        )
