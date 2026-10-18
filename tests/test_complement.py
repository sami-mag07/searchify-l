import time

from searchify import complement


def test_tavily_answers_within_budget():
    out, side, _ = complement._race(lambda: ["tavily hit"], lambda: ["searchify hit"], budget=1.0)
    assert (out, side) == (["tavily hit"], "tavily")


def test_slow_tavily_hands_over_to_searchify():
    def slow():
        time.sleep(1.5)
        return ["late tavily hit"]
    out, side, took = complement._race(slow, lambda: ["searchify hit"], budget=0.2)
    assert out == ["searchify hit"] and side.startswith("searchify") and took < 1.2


def test_failed_tavily_hands_over_to_searchify():
    def broken():
        raise RuntimeError("tavily down")
    out, side, _ = complement._race(broken, lambda: ["searchify hit"], budget=1.0)
    assert (out, side) == (["searchify hit"], "searchify")


def test_local_mode_never_uses_tavily(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setenv("SEARCHIFY_MODE", "local")
    complement.local_only()
    assert not complement.has_tavily()
