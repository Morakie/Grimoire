"""Pack drafts: dealing, passing, rounds, timers and pack bots (pure Python, no server needed)."""
import random
from datetime import datetime, timedelta, timezone

import pytest

import packdraft as pd
from draftbot.features import build_card_index
from draftbot.packbot import choose_from_pack, rank_pack
from tests.test_draftbot import synthetic_cube


def draft(num_seats=4, rounds=3, size=15, timer="shrinking", at="2026-01-01T00:00:00+00:00"):
    cube = synthetic_cube()        # 125 cards
    d = {"num_seats": num_seats, "picks": [], "cube": cube}
    d["packs"] = pd.new_state(cube, num_seats, rounds, size, timer, random.Random(3), at)
    return d


def test_deal_sizes_and_too_small_cube():
    d = draft(num_seats=8, rounds=3, size=5)
    dealt = [c for r in d["packs"]["deal"].values() for p in r.values() for c in p]
    assert len(dealt) == 120 and len(set(dealt)) == 120
    with pytest.raises(ValueError):
        pd.deal(synthetic_cube(), 8, 3, 15)


def test_passing_direction_and_queues():
    d = draft(num_seats=4, size=3)
    st = d["packs"]
    first = pd.pack_for(st, 0)
    pd.apply_pick(d, 0, first[0])
    # Round 1 passes left: seat 0's pack goes to seat 1, which now has two packs waiting.
    assert st["queues"]["0"] == [] and st["queues"]["1"] == ["0-1", "0-0"]
    assert pd.pack_for(st, 1) == st["contents"]["0-1"]
    with pytest.raises(ValueError):
        pd.apply_pick(d, 0, first[1])           # no pack in front of seat 0 now
    with pytest.raises(ValueError):
        pd.apply_pick(d, 1, first[1])           # not in seat 1's head pack


def test_full_draft_rounds_and_reversal():
    d = draft(num_seats=4, rounds=3, size=3)
    st = d["packs"]
    rng = random.Random(1)
    rounds_seen = []
    while not pd.is_complete(st):
        seat = rng.choice(pd.seats_waiting(st))
        if st["round"] not in rounds_seen:
            rounds_seen.append(st["round"])
        pd.apply_pick(d, seat, pd.pack_for(st, seat)[0])
    assert rounds_seen == [0, 1, 2]
    assert len(d["picks"]) == 4 * 3 * 3
    for s in range(4):
        assert sum(1 for p in d["picks"] if p["seat_index"] == s) == 9
    assert pd.direction(1) == -1 and pd.direction(2) == 1
    assert pd.public_view(d)["complete"] is True


def test_shrinking_timer_and_overdue():
    t0 = "2026-01-01T00:00:00+00:00"
    d = draft(num_seats=2, size=15, at=t0)
    st = d["packs"]
    assert pd.pick_seconds(15) == 80 and pd.pick_seconds(1) == 10
    dl = datetime.fromisoformat(pd.deadline(st, 0))
    assert dl - datetime.fromisoformat(t0) == timedelta(seconds=80)
    assert pd.overdue(st, (dl - timedelta(seconds=1)).isoformat()) == []
    assert pd.overdue(st, dl.isoformat()) == [0, 1]
    off = draft(num_seats=2, timer="off", at=t0)
    assert pd.deadline(off["packs"], 0) is None and pd.overdue(off["packs"], "2030-01-01T00:00:00+00:00") == []


def test_private_view_shows_only_own_seat():
    d = draft(num_seats=3, size=4)
    view = pd.private_view(d, [1])
    assert list(view) == ["1"] and len(view["1"]["pack"]) == 4 and view["1"]["deadline"]
    pub = pd.public_view(d)
    assert all("pack" not in s for s in pub["seats"]) and pub["direction"] == "left"


def test_pack_bots_draft_coherent_decks():
    from draftbot.engine import best_pair, _lane_fit
    cube = synthetic_cube(n_per_colour=40)        # 205 cards
    index = build_card_index(cube)
    d = {"num_seats": 8, "picks": [], "cube": cube}
    d["packs"] = pd.new_state(cube, 8, 3, 8, "off", random.Random(7))
    rng = random.Random(2)
    choices = by_choice_off = 0
    while not pd.is_complete(d["packs"]):
        for seat in pd.seats_waiting(d["packs"]):
            owned = [p["card_id"] for p in d["picks"] if p["seat_index"] == seat]
            pack = pd.pack_for(d["packs"], seat)
            pick = choose_from_pack(index, owned, pack, 24, rng=rng)
            if len(owned) >= 12:                  # committed: count off-colour picks made by choice
                pair = best_pair([index[i] for i in owned])
                if any(_lane_fit(index[i], pair) >= 1 for i in pack):
                    choices += 1
                    by_choice_off += _lane_fit(index[pick], pair) < 1
            pd.apply_pick(d, seat, pick, bot=True)
    assert by_choice_off <= 0.15 * choices, (by_choice_off, choices)
    # Every bot has at least half its pool in its two colours (late picks are often forced off-colour).
    for seat in range(8):
        owned = [index[p["card_id"]] for p in d["picks"] if p["seat_index"] == seat]
        pair = best_pair(owned)
        assert sum(1 for c in owned if not c.is_land and c.need and c.need <= pair) >= 12, seat


def test_rank_pack_prefers_power_early_and_colour_late():
    cube = synthetic_cube()
    index = build_card_index(cube)
    ids = [c["id"] for c in cube if c["id"][0] in "UR" and not c["id"].startswith("land")]
    strongest = max(ids, key=lambda i: index[i].power)
    assert rank_pack(index, [], ids, 45)[0][1] == strongest
    owned = [f"U{i}" for i in range(12)]
    pack = ["U20", "R20"]
    index["R20"].power, index["U20"].power = 0.8, 0.6
    assert rank_pack(index, owned, pack, 45)[0][1] == "U20"
