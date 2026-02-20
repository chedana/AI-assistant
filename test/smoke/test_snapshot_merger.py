from __future__ import annotations

from agent.merger import derive_snapshot, push_history
from agent.state import QuerySnapshot


def _base_snapshot() -> QuerySnapshot:
    return QuerySnapshot(
        location_keywords=["Waterloo"],
        layout_options=[{"bedrooms": 1, "bathrooms": 1, "property_type": "flat", "layout_tag": None, "max_rent_pcm": None}],
        max_rent_pcm=3500.0,
        available_from="2026-03-01",
        furnish_type="furnished",
        let_type="long term",
        min_tenancy_months=12.0,
        min_size_sqm=60.0,
        results=[{"listing_id": "A"}],
    )


def test_derive_snapshot_set_override_and_inherit() -> None:
    old = _base_snapshot()
    out = derive_snapshot(
        old_snapshot=old,
        set_fields={"max_rent_pcm": 3000.0, "furnish_type": "unfurnished"},
        clear_fields=[],
        is_reset=False,
    )
    assert out.max_rent_pcm == 3000.0
    assert out.furnish_type == "unfurnished"
    # Inherit untouched fields.
    assert out.location_keywords == ["Waterloo"]
    assert out.available_from == "2026-03-01"


def test_derive_snapshot_clear_only_selected_fields() -> None:
    old = _base_snapshot()
    out = derive_snapshot(
        old_snapshot=old,
        set_fields={},
        clear_fields=["furnish_type", "min_size_sqm", "layout_options"],
        is_reset=False,
    )
    assert out.furnish_type is None
    assert out.min_size_sqm is None
    assert out.layout_options == []
    # Unrelated fields stay.
    assert out.max_rent_pcm == 3500.0
    assert out.location_keywords == ["Waterloo"]


def test_derive_snapshot_clear_wins_when_set_and_clear_same_field() -> None:
    old = _base_snapshot()
    out = derive_snapshot(
        old_snapshot=old,
        set_fields={"max_rent_pcm": 2800.0},
        clear_fields=["max_rent_pcm"],
        is_reset=False,
    )
    assert out.max_rent_pcm is None


def test_push_history_hit_promotes_existing_snapshot() -> None:
    a = _base_snapshot()
    b = derive_snapshot(old_snapshot=a, set_fields={"max_rent_pcm": 3000.0}, clear_fields=[], is_reset=False)
    c = derive_snapshot(old_snapshot=a, set_fields={"max_rent_pcm": 2600.0}, clear_fields=[], is_reset=False)
    history = [a, b, c]

    out, hit = push_history(history, b, max_size=5)
    assert hit is True
    assert len(out) == 3
    assert out[0].get_hash() == b.get_hash()
    assert sum(1 for x in out if x.get_hash() == b.get_hash()) == 1


def test_snapshot_hash_is_stable_under_order_variations() -> None:
    s1 = QuerySnapshot(
        location_keywords=["Waterloo", "Canary Wharf"],
        layout_options=[
            {"bedrooms": 2, "bathrooms": 2, "property_type": "flat", "layout_tag": None, "max_rent_pcm": 3200.0},
            {"bedrooms": 1, "bathrooms": 1, "property_type": "flat", "layout_tag": None, "max_rent_pcm": 2800.0},
        ],
    )
    s2 = QuerySnapshot(
        location_keywords=["Canary Wharf", "Waterloo"],
        layout_options=[
            {"bedrooms": 1, "bathrooms": 1, "property_type": "flat", "layout_tag": None, "max_rent_pcm": 2800.0},
            {"bedrooms": 2, "bathrooms": 2, "property_type": "flat", "layout_tag": None, "max_rent_pcm": 3200.0},
        ],
    )
    assert s1.get_hash() == s2.get_hash()
