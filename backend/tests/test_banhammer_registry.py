from app.models.enums import MatchMode
from app.services.banhammer.registry import Blacklist, Rule


def bl(*patterns: str, mode: MatchMode = MatchMode.contains) -> Blacklist:
    return Blacklist(rules=[Rule(p, mode) for p in patterns])


def test_contains_matches_subgenres():
    v = bl("rap").evaluate("t1", "a1", {"artist1": ["french rap", "pop"]})
    assert v.banned and v.genre == "french rap" and v.rule == "rap"


def test_exact_does_not_match_subgenre():
    v = bl("rap", mode=MatchMode.exact).evaluate("t1", "a1", {"artist1": ["trap"]})
    assert not v.banned


def test_regex_mode():
    b = Blacklist(rules=[Rule(r"^(hip ?hop|trap)$", MatchMode.regex)])
    assert b.evaluate("t", "a", {"x": ["hip hop"]}).banned
    assert b.evaluate("t", "a", {"x": ["hiphop"]}).banned
    assert not b.evaluate("t", "a", {"x": ["hip hop soul"]}).banned


def test_exemptions_win():
    b = bl("rap")
    b.exempt_artist_ids.add("artist1")
    assert not b.evaluate("t1", "a1", {"artist1": ["rap"]}).banned
    b2 = bl("rap")
    b2.exempt_track_ids.add("t1")
    assert not b2.evaluate("t1", "a1", {"artist1": ["rap"]}).banned


def test_banned_artist_regardless_of_genre():
    b = Blacklist(banned_artist_ids={"artist9"})
    v = b.evaluate("t", "a", {"artist9": ["classical"]})
    assert v.banned and v.reason == "banned_artist"


def test_rule_scope_flags():
    b = Blacklist(rules=[Rule("rap", MatchMode.contains, skip_guard=False, purge=True)])
    assert not b.evaluate("t", "a", {"x": ["rap"]}, context="skip_guard").banned
    assert b.evaluate("t", "a", {"x": ["rap"]}, context="purge").banned
