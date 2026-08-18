"""Tests unitaires — core/validators.py"""

import pytest

from core.validators import safe_path, valid_hash, valid_hashes

VALID_HASH = "a" * 40
VALID_HASH_2 = "b" * 40


class TestValidHash:
    def test_valid_40_hex(self):
        assert valid_hash(VALID_HASH)

    def test_valid_uppercase(self):
        assert valid_hash("A" * 40)

    def test_valid_mixed_case(self):
        assert valid_hash("aAbBcCdD" * 5)

    def test_empty_string(self):
        assert not valid_hash("")

    def test_too_short(self):
        assert not valid_hash("a" * 39)

    def test_too_long(self):
        assert not valid_hash("a" * 41)

    def test_invalid_chars(self):
        assert not valid_hash("g" * 40)  # 'g' n'est pas hex

    def test_spaces(self):
        assert not valid_hash(" " * 40)


class TestValidHashes:
    def test_single_valid(self):
        assert valid_hashes([VALID_HASH])

    def test_multiple_valid(self):
        assert valid_hashes([VALID_HASH, VALID_HASH_2])

    def test_empty_list(self):
        assert not valid_hashes([])

    def test_one_invalid(self):
        assert not valid_hashes([VALID_HASH, "invalid"])

    def test_all_invalid(self):
        assert not valid_hashes(["bad", "also-bad"])


class TestSafePath:
    def test_simple_path(self):
        assert safe_path("/home/user/downloads")

    def test_windows_path(self):
        assert safe_path("C:/Users/Pierre/Downloads")

    def test_relative_path(self):
        assert safe_path("downloads/subfolder")

    def test_traversal_unix(self):
        assert not safe_path("/home/user/../etc/passwd")

    def test_traversal_windows(self):
        assert not safe_path("C:\\Users\\..\\Windows\\System32")

    def test_traversal_mixed(self):
        assert not safe_path("/data/../secret")

    def test_dot_in_filename(self):
        assert safe_path("/home/user/file.txt")

    def test_double_dot_in_name(self):
        # "..secret" est OK, seul ".." seul est dangereux
        assert safe_path("/home/user/..hidden")
