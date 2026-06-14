"""
tests/test_tools.py

Isolation tests for each FitFindr tool, including one test per failure mode.
Run with: pytest tests/
"""

import pytest
from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── search_listings ───────────────────────────────────────────────────────────

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0

def test_search_returns_dicts_with_expected_fields():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    item = results[0]
    for field in ["id", "title", "description", "category", "style_tags",
                  "size", "condition", "price", "colors", "platform"]:
        assert field in item, f"Missing field: {field}"

def test_search_empty_results_no_exception():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []

def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=10)
    assert all(item["price"] <= 10 for item in results)

def test_search_price_filter_excludes_above_max():
    results = search_listings("tee", size=None, max_price=20)
    assert all(item["price"] <= 20 for item in results)

def test_search_size_filter():
    results = search_listings("jacket", size="M", max_price=None)
    assert all("m" in item["size"].lower() for item in results)

def test_search_sorted_by_relevance():
    results = search_listings("graphic tee", size=None, max_price=None)
    assert len(results) > 0
    # Top result should have "graphic tee" in style_tags or title
    top = results[0]
    searchable = " ".join(top.get("style_tags", [])) + " " + top.get("title", "")
    assert "graphic" in searchable.lower() or "tee" in searchable.lower()

def test_search_no_description_match_returns_empty():
    results = search_listings("xyznotarealitem12345", size=None, max_price=None)
    assert results == []

def test_search_none_filters_return_all_matches():
    results = search_listings("vintage", size=None, max_price=None)
    assert len(results) > 0


# ── suggest_outfit ────────────────────────────────────────────────────────────

def _get_sample_item():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert results, "search_listings returned nothing — check test data"
    return results[0]

def test_suggest_outfit_with_wardrobe_returns_string():
    item = _get_sample_item()
    result = suggest_outfit(item, get_example_wardrobe())
    assert isinstance(result, str)
    assert len(result) > 0

def test_suggest_outfit_empty_wardrobe_no_exception():
    item = _get_sample_item()
    result = suggest_outfit(item, get_empty_wardrobe())
    assert isinstance(result, str)
    assert len(result) > 0

def test_suggest_outfit_empty_wardrobe_returns_useful_string():
    item = _get_sample_item()
    result = suggest_outfit(item, get_empty_wardrobe())
    # Must not be empty or whitespace-only
    assert result.strip() != ""
    # Must not be the fallback crash message
    assert "error" not in result.lower() or len(result) > 50


# ── create_fit_card ───────────────────────────────────────────────────────────

def test_create_fit_card_returns_string():
    item = _get_sample_item()
    outfit = "Pair this tee with your baggy jeans and chunky white sneakers."
    result = create_fit_card(outfit, item)
    assert isinstance(result, str)
    assert len(result) > 0

def test_create_fit_card_empty_outfit_returns_error_string():
    item = _get_sample_item()
    result = create_fit_card("", item)
    assert isinstance(result, str)
    assert "cannot" in result.lower() or "without" in result.lower()

def test_create_fit_card_whitespace_outfit_returns_error_string():
    item = _get_sample_item()
    result = create_fit_card("   ", item)
    assert isinstance(result, str)
    assert len(result) > 0
    # Should not have called LLM — check it's the guard message
    assert "cannot" in result.lower() or "without" in result.lower()

def test_create_fit_card_no_exception_on_valid_input():
    item = _get_sample_item()
    outfit = "Style this with wide-leg jeans and platform sneakers for a 90s look."
    result = create_fit_card(outfit, item)
    assert isinstance(result, str)
    assert len(result) > 10
