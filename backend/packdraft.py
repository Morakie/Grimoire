"""Pack drafts: deal packs from a cube, simultaneous picks, passing, timers.

Pure logic on plain dicts (no database), so it is easy to test. `server.py` loads the draft, calls these
functions, and saves the result with a revision check so simultaneous picks don't overwrite each other.

State (draft["packs"]):
    round        current round, 0-based
    rounds       number of rounds (packs per player)
    deal         {round: {seat: [card ids]}} dealt at the start, used as each round opens
    queues       {seat: [pack ids]} packs waiting in front of each seat, head first
    contents     {pack id: [card ids]} cards left in each open pack
    since        {seat: iso time} when the seat's head pack arrived (for the timer)
    timer        "shrinking" or "off"
Picks are appended to draft["picks"] as {seat_index, card_id, round, pick, ts, auto?, bot?}.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

TIMERS = ("shrinking", "off")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def pick_seconds(cards_in_pack: int) -> int:
    """Shrinking timer: about 80 s for a full 15-card pack down to 10 s for the last card."""
    return max(10, 5 * cards_in_pack + 5)


def direction(round_no: int) -> int:
    """Pack 1 passes left, pack 2 right, pack 3 left, and so on."""
    return 1 if round_no % 2 == 0 else -1


def cards_needed(num_seats: int, rounds: int, pack_size: int) -> int:
    return num_seats * rounds * pack_size


def deal(cube: List[dict], num_seats: int, rounds: int, pack_size: int, rng: Optional[random.Random] = None) -> Dict[str, Dict[str, List[str]]]:
    """Shuffle the cube and deal `rounds` packs of `pack_size` to every seat. Extra cards are left out."""
    rng = rng or random.Random()
    ids = [c["id"] for c in cube]
    rng.shuffle(ids)
    need = cards_needed(num_seats, rounds, pack_size)
    if len(ids) < need:
        raise ValueError(f"The cube has {len(ids)} cards; {num_seats} seats × {rounds} packs × {pack_size} cards needs {need}.")
    out: Dict[str, Dict[str, List[str]]] = {}
    i = 0
    for r in range(rounds):
        out[str(r)] = {}
        for s in range(num_seats):
            out[str(r)][str(s)] = ids[i:i + pack_size]
            i += pack_size
    return out


def new_state(cube: List[dict], num_seats: int, rounds: int, pack_size: int, timer: str = "shrinking",
              rng: Optional[random.Random] = None, at: Optional[str] = None) -> dict:
    st = {
        "round": 0, "rounds": rounds, "pack_size": pack_size,
        "timer": timer if timer in TIMERS else "shrinking",
        "deal": deal(cube, num_seats, rounds, pack_size, rng),
        "queues": {}, "contents": {}, "since": {},
    }
    _open_round(st, num_seats, at or now_iso())
    return st


def _open_round(st: dict, num_seats: int, at: str) -> None:
    r = st["round"]
    st["queues"] = {}
    st["contents"] = {}
    st["since"] = {}
    for s in range(num_seats):
        pid = f"{r}-{s}"
        st["contents"][pid] = list(st["deal"][str(r)][str(s)])
        st["queues"][str(s)] = [pid]
        st["since"][str(s)] = at


def head_pack(st: dict, seat: int) -> Optional[str]:
    q = st["queues"].get(str(seat)) or []
    return q[0] if q else None


def pack_for(st: dict, seat: int) -> List[str]:
    pid = head_pack(st, seat)
    return list(st["contents"].get(pid, [])) if pid else []


def deadline(st: dict, seat: int) -> Optional[str]:
    """When the seat's current pick times out (None with the timer off or no pack waiting)."""
    if st.get("timer") == "off":
        return None
    pid = head_pack(st, seat)
    if not pid or str(seat) not in st["since"]:
        return None
    started = datetime.fromisoformat(st["since"][str(seat)])
    return (started + timedelta(seconds=pick_seconds(len(st["contents"][pid])))).isoformat()


def is_complete(st: dict) -> bool:
    return st["round"] >= st["rounds"]


def apply_pick(d: dict, seat: int, card_id: str, at: Optional[str] = None, **flags) -> None:
    """Take `card_id` from the pack in front of `seat`, pass the rest on, and open the next round when
    every pack is empty. Raises ValueError for an invalid pick. Mutates `d` (the draft document)."""
    st = d["packs"]
    at = at or now_iso()
    if is_complete(st):
        raise ValueError("The draft is over")
    pid = head_pack(st, seat)
    if not pid:
        raise ValueError("No pack in front of this seat yet")
    contents = st["contents"][pid]
    if card_id not in contents:
        raise ValueError("That card isn't in your pack")
    n = d["num_seats"]
    round_no = st["round"]
    pick_no = st["pack_size"] - len(contents) + 1     # 1-based pick within this pack round
    contents.remove(card_id)
    d.setdefault("picks", []).append({"seat_index": seat, "card_id": card_id, "round": round_no, "pick": pick_no,
                                      "order": len(d["picks"]), "ts": at, **{k: v for k, v in flags.items() if v}})
    st["queues"][str(seat)].pop(0)
    if st["queues"][str(seat)]:
        st["since"][str(seat)] = at                   # next pack was already waiting: its clock starts now
    else:
        st["since"].pop(str(seat), None)
    if contents:
        nxt = (seat + direction(round_no)) % n
        q = st["queues"].setdefault(str(nxt), [])
        q.append(pid)
        if len(q) == 1:
            st["since"][str(nxt)] = at
    else:
        del st["contents"][pid]
    if not st["contents"]:                             # every pack in this round is empty
        st["round"] += 1
        if is_complete(st):
            st["queues"], st["since"] = {}, {}
        else:
            _open_round(st, n, at)


def seats_waiting(st: dict) -> List[int]:
    return sorted(int(s) for s, q in st["queues"].items() if q)


def overdue(st: dict, at: Optional[str] = None) -> List[int]:
    """Seats whose pick timer has run out."""
    if st.get("timer") == "off":
        return []
    t = datetime.fromisoformat(at) if at else datetime.now(timezone.utc)
    out = []
    for s in seats_waiting(st):
        dl = deadline(st, s)
        if dl and datetime.fromisoformat(dl) <= t:
            out.append(s)
    return out


def public_view(d: dict) -> dict:
    """What everyone may see: round, direction, and how many packs/cards are in front of each seat."""
    st = d["packs"]
    seats = []
    for s in range(d["num_seats"]):
        q = st["queues"].get(str(s)) or []
        seats.append({
            "seat": s,
            "waiting": len(q),
            "cards_in_pack": len(st["contents"].get(q[0], [])) if q else 0,
            "picks": sum(1 for p in d.get("picks", []) if p["seat_index"] == s),
        })
    return {
        "round": min(st["round"] + 1, st["rounds"]),        # 1-based for display
        "rounds": st["rounds"], "pack_size": st["pack_size"], "timer": st["timer"],
        "direction": "left" if direction(st["round"]) == 1 else "right",
        "complete": is_complete(st), "seats": seats,
    }


def private_view(d: dict, seats: List[int]) -> dict:
    """What one player sees for their own seats: the pack in front of each, its deadline, their picks."""
    st = d["packs"]
    out = {}
    for s in seats:
        q = st["queues"].get(str(s)) or []
        out[str(s)] = {
            "pack": pack_for(st, s),
            "waiting": len(q),
            "deadline": deadline(st, s),
            "picks": [p["card_id"] for p in d.get("picks", []) if p["seat_index"] == s],
        }
    return out
