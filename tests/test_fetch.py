from scraper import fetch


def test_browser_pauses_between_pages_but_not_before_the_first(monkeypatch):
    slept = []
    monkeypatch.setattr(fetch.time, "sleep", slept.append)
    monkeypatch.setattr(fetch.random, "uniform", lambda a, b: (a + b) / 2)
    b = fetch.Browser()  # default 5-10 s
    for _ in range(3):
        b._wait_between_pages()
    assert slept == [7.5, 7.5]


def test_browser_pause_can_be_disabled(monkeypatch):
    slept = []
    monkeypatch.setattr(fetch.time, "sleep", slept.append)
    b = fetch.Browser(pause=(0, 0))
    b._wait_between_pages(); b._wait_between_pages()
    assert slept == []
