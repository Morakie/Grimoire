"""Bots for pack drafts: pick the best card from the pack in front of them.

Uses the same card knowledge as the rotisserie bots (power, colour lanes, fixing, combos, CubeCobra
package partners) but a simpler pick rule, because in a pack draft you only choose from one pack and
can't see the whole pool. Early on a bot takes the strongest card; as its picks pile up it leans into
its best colours. A small amount of randomness (persona-free) keeps drafts from being identical.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional

from .combos import Combo
from .engine import TUNING, _lane_fit, best_pair, card_fit, combo_value, lane_distribution, partner_value
from .features import CardInfo


def rank_pack(index: Dict[str, CardInfo], owned_ids: List[str], pack_ids: List[str], total_picks: int,
              combos: Optional[List[Combo]] = None) -> List[tuple]:
    """Score every card in the pack for a drafter who owns `owned_ids`. Returns [(score, id)], best first.
    Cards the index doesn't know (custom cards) score last."""
    combos = combos or []
    owned = [index[i] for i in owned_ids if i in index]
    n = len(owned)
    progress = n / max(total_picks, 1)
    dist = lane_distribution(owned, n)
    # How much colours matter: nothing for the first few picks, nearly everything by mid-draft.
    w = max(0.0, min(0.9, (n - 2) / 10))
    # Commitment: from about pick 5 the bot settles on its best two colours, fully by about pick 13.
    commit = max(0.0, min(1.0, (n - 4) / 8))
    pair = best_pair(owned) if commit > 0 else None
    fit_cache: Dict[str, float] = {}

    def fit_of(cid: str) -> float:
        if cid not in fit_cache:
            card = index.get(cid)
            if card is None:
                fit_cache[cid] = 0.0
            else:
                soft = card_fit(card, dist)
                fit_cache[cid] = soft if pair is None else (1 - commit) * soft + commit * _lane_fit(card, pair)
        return fit_cache[cid]

    owned_set = {c.id for c in owned}
    pack_set = set(pack_ids)
    out = []
    for cid in pack_ids:
        card = index.get(cid)
        if card is None:
            out.append((-1.0, cid))
            continue
        fit = fit_of(cid)
        power = card.power
        if card.is_fixing:
            # Duals are worth less early and more once the bot knows its colours.
            power *= TUNING["early_fixing_damp"] + (1 - TUNING["early_fixing_damp"]) * min(1.0, progress * 2)
            power += TUNING["fixing_bonus"] * fit * progress
        score = power * ((1 - w) + w * fit)
        if combos and card.combos:
            score += 0.5 * combo_value(card, owned_set, pack_set | owned_set, combos, fit_of)
        if card.partners:
            score += TUNING["partner_weight"] * partner_value(card, owned_set, fit_of)
        out.append((score, cid))
    out.sort(reverse=True)
    return out


def choose_from_pack(index: Dict[str, CardInfo], owned_ids: List[str], pack_ids: List[str], total_picks: int,
                     combos: Optional[List[Combo]] = None, rng: Optional[random.Random] = None) -> str:
    """The bot's pick: usually the top card, sometimes a near-equal second for variety."""
    ranked = rank_pack(index, owned_ids, pack_ids, total_picks, combos)
    if not ranked:
        raise ValueError("Empty pack")
    rng = rng or random.Random()
    if len(ranked) > 1 and ranked[1][0] >= 0 and ranked[0][0] - ranked[1][0] < 0.03 and rng.random() < 0.35:
        return ranked[1][1]
    return ranked[0][1]
