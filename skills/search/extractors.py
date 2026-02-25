"""Re-export facade — all public names forwarded from split modules.

This file preserves backward compatibility so that existing
``from skills.search.extractors import …`` statements continue to work.
Consumers should migrate to import directly from the new modules:

  - skills.search.text_utils
  - skills.search.location_match
  - skills.search.constraint_extraction
  - skills.search.constraint_ops
"""

# --- text_utils ----------------------------------------------------------
from skills.search.text_utils import (  # noqa: F401
    _norm_furnish_value,
    _norm_property_type_value,
    _safe_text,
    _to_float,
    _truthy_env,
    parse_jsonish_items,
)

# --- location_match ------------------------------------------------------
from skills.search.location_match import (  # noqa: F401
    _correct_location_keyword,
    _normalize_location_keyword,
    expand_location_keyword_candidates,
)

# --- constraint_extraction -----------------------------------------------
from skills.search.constraint_extraction import (  # noqa: F401
    _extract_json_obj,
    _extract_layout_options_candidates,
    _infer_append_mode_from_query,
    _infer_available_from_from_text,
    _infer_bed_bath_compact_from_query,
    _infer_clear_location_from_query,
    _infer_float_eq_from_patterns,
    _infer_furnish_type_from_query,
    _infer_layout_options_from_query,
    _infer_layout_remove_ops_from_query,
    _infer_let_type_from_text,
    _infer_max_rent_pcm_from_query,
    _infer_min_tenancy_months_from_text,
    _infer_numeric_eq_from_patterns,
    _infer_property_type_from_query,
    _infer_replace_all_from_query,
    _infer_replace_mode_from_query,
    _normalize_constraint_extract,
    _normalize_layout_options,
    _normalize_semantic_extract,
    _parse_user_date_uk_first,
    repair_extracted_constraints,
)

# --- constraint_ops ------------------------------------------------------
from skills.search.constraint_ops import (  # noqa: F401
    _canon_for_structured_compare,
    _normalize_for_structured_policy,
    compact_constraints_view,
    merge_constraints,
    normalize_budget_to_pcm,
    normalize_constraints,
    summarize_constraint_changes,
)
