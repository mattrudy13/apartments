from datetime import date

from scraper import run


def test_retry_slugs_only_todays_failures():
    status = {
        "a": {"last_attempt": "2026-10-12", "ok": False},
        "b": {"last_attempt": "2026-10-12", "ok": True},
        "c": {"last_attempt": "2026-10-05", "ok": False},  # failed last week: not today's retry
    }
    assert run.retry_slugs(status, date(2026, 10, 12)) == ["a"]
    # launchd fires a missed 14:00 job on the next wake; a day later there's nothing to retry.
    assert run.retry_slugs(status, date(2026, 10, 13)) == []
