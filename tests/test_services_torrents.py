"""Tests unitaires — services/torrents.py"""

import pytest

from services.torrents import filter_and_sort

H = "a" * 40

SAMPLE: list[dict] = [
    {
        "hash": "a" * 40, "name": "Alpha", "category": "movies",
        "state": "downloading", "size": 100, "dlspeed": 500,
        "upspeed": 0, "num_seeds": 10, "num_leechs": 2, "ratio": 0.5,
        "added_on": 1000,
    },
    {
        "hash": "b" * 40, "name": "Beta", "category": "tv",
        "state": "pausedDL", "size": 200, "dlspeed": 0,
        "upspeed": 0, "num_seeds": 5, "num_leechs": 0, "ratio": 1.2,
        "added_on": 2000,
    },
    {
        "hash": "c" * 40, "name": "Gamma", "category": "movies",
        "state": "uploading", "size": 300, "dlspeed": 0,
        "upspeed": 100, "num_seeds": 0, "num_leechs": 0, "ratio": 2.0,
        "added_on": 3000,
    },
]


class TestFiltering:
    def test_no_filter_returns_all(self):
        assert len(filter_and_sort(SAMPLE)) == 3

    def test_search_by_name(self):
        result = filter_and_sort(SAMPLE, search="alpha")
        assert len(result) == 1
        assert result[0]["name"] == "Alpha"

    def test_search_case_insensitive(self):
        # filter_and_sort normalise la casse en interne
        result = filter_and_sort(SAMPLE, search="BETA")
        assert len(result) == 1
        assert result[0]["name"] == "Beta"

    def test_search_partial_match(self):
        # "amma" est contenu dans "Gamma" uniquement
        result = filter_and_sort(SAMPLE, search="amma")
        assert len(result) == 1
        assert result[0]["name"] == "Gamma"

    def test_search_no_match(self):
        assert filter_and_sort(SAMPLE, search="xyz") == []

    def test_filter_category(self):
        result = filter_and_sort(SAMPLE, category="movies")
        assert len(result) == 2
        assert all(t["category"] == "movies" for t in result)

    def test_filter_category_no_match(self):
        assert filter_and_sort(SAMPLE, category="anime") == []

    def test_filter_state(self):
        result = filter_and_sort(SAMPLE, state="pausedDL")
        assert len(result) == 1
        assert result[0]["name"] == "Beta"

    def test_combined_search_and_category(self):
        result = filter_and_sort(SAMPLE, search="a", category="movies")
        # Alpha (movies, contains 'a') et Gamma (movies, contains 'a')
        assert len(result) == 2

    def test_combined_category_and_state(self):
        result = filter_and_sort(SAMPLE, category="movies", state="downloading")
        assert len(result) == 1
        assert result[0]["name"] == "Alpha"

    def test_empty_data(self):
        assert filter_and_sort([], search="alpha") == []


class TestSortingString:
    def test_sort_name_asc(self):
        result = filter_and_sort(SAMPLE, order_col=1, order_dir="asc")
        assert [t["name"] for t in result] == ["Alpha", "Beta", "Gamma"]

    def test_sort_name_desc(self):
        result = filter_and_sort(SAMPLE, order_col=1, order_dir="desc")
        assert [t["name"] for t in result] == ["Gamma", "Beta", "Alpha"]

    def test_sort_category_asc(self):
        result = filter_and_sort(SAMPLE, order_col=2, order_dir="asc")
        # movies < tv alphabétiquement
        assert result[0]["category"] == "movies"
        assert result[-1]["category"] == "tv"

    def test_sort_state_asc(self):
        result = filter_and_sort(SAMPLE, order_col=5, order_dir="asc")
        # downloading < pausedDL < uploading
        assert result[0]["state"] == "downloading"


class TestSortingNumeric:
    def test_sort_size_asc(self):
        result = filter_and_sort(SAMPLE, order_col=3, order_dir="asc")
        assert result[0]["size"] == 100
        assert result[-1]["size"] == 300

    def test_sort_size_desc(self):
        result = filter_and_sort(SAMPLE, order_col=3, order_dir="desc")
        assert result[0]["size"] == 300

    def test_sort_seeds_desc(self):
        result = filter_and_sort(SAMPLE, order_col=6, order_dir="desc")
        assert result[0]["num_seeds"] == 10

    def test_sort_dlspeed_desc(self):
        result = filter_and_sort(SAMPLE, order_col=8, order_dir="desc")
        assert result[0]["dlspeed"] == 500

    def test_sort_ratio_desc(self):
        result = filter_and_sort(SAMPLE, order_col=10, order_dir="desc")
        assert result[0]["ratio"] == 2.0

    def test_sort_added_on_asc(self):
        result = filter_and_sort(SAMPLE, order_col=12, order_dir="asc")
        assert result[0]["added_on"] == 1000
        assert result[-1]["added_on"] == 3000

    def test_missing_numeric_field_treated_as_zero(self):
        data = [
            {"hash": "a" * 40, "name": "A", "size": 50},
            {"hash": "b" * 40, "name": "B"},  # pas de 'size'
        ]
        result = filter_and_sort(data, order_col=3, order_dir="asc")
        assert result[0].get("size", 0) == 0
