"""Tests unitaires — core/cache.py (_TorrentCache)"""

import time

import pytest

from core.cache import _TorrentCache
from core.config import CACHE_TTL


@pytest.fixture
def cache():
    c = _TorrentCache()
    c.set([
        {"hash": "aaaa" * 10, "name": "Alpha", "state": "downloading", "category": "movies"},
        {"hash": "bbbb" * 10, "name": "Beta",  "state": "pausedDL",    "category": "tv"},
        {"hash": "cccc" * 10, "name": "Gamma", "state": "uploading",   "category": "movies"},
    ])
    return c


class TestBasicOperations:
    def test_set_and_get(self, cache):
        data = cache.get()
        assert len(data) == 3

    def test_is_ready_after_set(self, cache):
        assert cache.is_ready()

    def test_is_not_ready_empty(self):
        c = _TorrentCache()
        assert not c.is_ready()

    def test_age_increases(self, cache):
        age1 = cache.age()
        time.sleep(0.05)
        age2 = cache.age()
        assert age2 > age1

    def test_invalidate_resets_age(self, cache):
        cache.set([{"hash": "a" * 40}])
        age_before = cache.age()
        cache.invalidate()
        # After invalidate, _ts=0.0 so age() >> age before invalidate
        assert cache.age() > age_before + CACHE_TTL

    def test_start_refresh_returns_true_first(self, cache):
        assert cache.start_refresh() is True

    def test_start_refresh_returns_false_while_refreshing(self, cache):
        cache.start_refresh()
        assert cache.start_refresh() is False

    def test_cancel_refresh_allows_restart(self, cache):
        cache.start_refresh()
        cache.cancel_refresh()
        assert cache.start_refresh() is True


class TestUpdateTorrent:
    def test_update_category(self, cache):
        cache.update_torrent("aaaa" * 10, category="anime")
        assert cache.get()[0]["category"] == "anime"

    def test_update_multiple_fields(self, cache):
        cache.update_torrent("bbbb" * 10, state="downloading", category="movies")
        t = next(t for t in cache.get() if t["hash"] == "bbbb" * 10)
        assert t["state"] == "downloading"
        assert t["category"] == "movies"

    def test_update_nonexistent_hash(self, cache):
        # Ne doit pas lever d'exception
        cache.update_torrent("zzzz" * 10, state="paused")
        assert len(cache.get()) == 3


class TestRemoveTorrents:
    def test_remove_one(self, cache):
        cache.remove_torrents({"aaaa" * 10})
        assert len(cache.get()) == 2
        assert all(t["hash"] != "aaaa" * 10 for t in cache.get())

    def test_remove_multiple(self, cache):
        cache.remove_torrents({"aaaa" * 10, "bbbb" * 10})
        assert len(cache.get()) == 1
        assert cache.get()[0]["hash"] == "cccc" * 10

    def test_remove_all(self, cache):
        cache.remove_torrents({"aaaa" * 10, "bbbb" * 10, "cccc" * 10})
        assert cache.get() == []

    def test_remove_nonexistent(self, cache):
        cache.remove_torrents({"zzzz" * 10})
        assert len(cache.get()) == 3


class TestApplyStateChange:
    def test_pause_downloading(self, cache):
        cache.apply_state_change({"aaaa" * 10}, "pause")
        t = next(t for t in cache.get() if t["hash"] == "aaaa" * 10)
        assert t["state"] == "pausedDL"

    def test_pause_uploading_becomes_pausedUP(self, cache):
        cache.apply_state_change({"cccc" * 10}, "pause")
        t = next(t for t in cache.get() if t["hash"] == "cccc" * 10)
        assert t["state"] == "pausedUP"

    def test_resume_pausedDL(self, cache):
        cache.apply_state_change({"bbbb" * 10}, "resume")
        t = next(t for t in cache.get() if t["hash"] == "bbbb" * 10)
        assert t["state"] == "downloading"

    def test_resume_pausedUP(self):
        c = _TorrentCache()
        c.set([{"hash": "aaaa" * 10, "state": "pausedUP"}])
        c.apply_state_change({"aaaa" * 10}, "resume")
        assert c.get()[0]["state"] == "uploading"

    def test_recheck(self, cache):
        cache.apply_state_change({"aaaa" * 10}, "recheck")
        t = next(t for t in cache.get() if t["hash"] == "aaaa" * 10)
        assert t["state"] == "checkingResumeData"

    def test_only_targeted_hash_changes(self, cache):
        cache.apply_state_change({"aaaa" * 10}, "pause")
        t_beta = next(t for t in cache.get() if t["hash"] == "bbbb" * 10)
        assert t_beta["state"] == "pausedDL"  # inchangé
