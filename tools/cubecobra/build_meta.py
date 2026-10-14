"""Build backend/data/cube_meta.json from CubeCobra's public data export.

What it produces (card names, never ids, so it works for any cube):
  archetypes: for each deck archetype seen in powered cubes (colours + plan, and plan alone), the cards
              real drafters put in those decks, as [name, rate %, lift]. "rate" counts only decks whose
              cube had the card; "lift" is how much more often than powered decks in general.
  synergy:    for each common card, the cards that show up in the same decks far more often than chance
              (again only counting decks where both were available), as [name, lift].

Source: s3://cubecobra-public/export/ (public, CubeCobra updates it every few months) plus Scryfall's
oracle-cards bulk file for colours and rules text. Runs monthly in GitHub Actions
(.github/workflows/cube-meta.yml); it does nothing when the export hasn't changed since the last run.

Needs Python 3.10+ and numpy. Usage:  python tools/cubecobra/build_meta.py --out backend/data/cube_meta.json
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np

BUCKET = "https://cubecobra-public.s3.amazonaws.com"
UA = {"User-Agent": "GrimoireCubeMeta/1.0", "Accept": "application/json;q=0.9,*/*;q=0.8"}   # Scryfall requires both
POWER = {"Black Lotus", "Mox Sapphire", "Mox Jet", "Mox Ruby", "Mox Pearl", "Mox Emerald",
         "Time Walk", "Ancestral Recall", "Timetwister"}
MIN_POWER_IN_CUBE = 3          # a "powered" cube runs at least this many of the Power Nine


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def get(url: str, retries: int = 4) -> bytes:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except Exception as exc:          # transient network errors: back off and retry
            if attempt == retries - 1:
                raise
            log("retry", url, exc)
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def get_json(url: str):
    raw = get(url)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw)


def list_keys(prefix: str):
    """(key, size, last_modified) for every object under a prefix (S3 ListObjectsV2, no auth)."""
    ns = "{http://s3.amazonaws.com/doc/2006-03-01/}"
    token, out = None, []
    while True:
        url = f"{BUCKET}/?list-type=2&prefix={prefix}" + (f"&continuation-token={urllib.parse.quote(token)}" if token else "")
        root = ET.fromstring(get(url))
        for c in root.findall(f"{ns}Contents"):
            out.append((c.find(f"{ns}Key").text, int(c.find(f"{ns}Size").text), c.find(f"{ns}LastModified").text))
        if root.find(f"{ns}IsTruncated").text != "true":
            return out
        token = root.find(f"{ns}NextContinuationToken").text


# ----------------------------------------------------------------------------------------- cards

ROLE = {
    "artifact_payoff": re.compile(r"for each artifact you control|whenever you cast an artifact|tap an untapped artifact|artifacts? you control"),
    "reanimate": re.compile(r"(return|put) (target |a |up to one )?(creature card|target card|the top creature card).{0,40}graveyard (to|onto) the battlefield|enchant creature card in a graveyard|from (a|your) graveyard onto the battlefield|put target creature card from a graveyard onto the battlefield"),
    "storm": re.compile(r"(^|\n)storm\b|\bstorm \("),
    "ritual": re.compile(r"add \{[wubrgc]\}\{[wubrgc]\}\{[wubrgc]\}"),
    "cheat": re.compile(r"put (a|an|that) (creature|artifact|permanent)? ?card from your hand onto the battlefield|put an artifact, creature, enchantment, or land card from their hand onto the battlefield|creature card from your hand onto the battlefield"),
    "counter": re.compile(r"counter target"),
    "removal": re.compile(r"(destroy|exile) target (creature|nonland|permanent|planeswalker)|deals? (\d+|x) damage to (any target|target creature)|target creature gets -\d"),
    "flicker": re.compile(r"exile (up to one )?(another |other )?target[^.]*(creature|permanent)s? you (control|own)[^.]*return|then return (it|that card|those cards) to the battlefield"),
    "ramp": re.compile(r"search your library for (a|up to \w+) (basic )?lands?"),
}
MANA = re.compile(r"add \{|add one mana|add (two|three) mana")


def load_scryfall():
    meta = json.loads(get("https://api.scryfall.com/bulk-data/oracle-cards"))
    url = meta.get("download_uri") or meta["jsonl_download_uri"]
    raw = get(url)
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    text = raw.decode()
    cards = json.loads(text) if text.lstrip().startswith("[") else [json.loads(l) for l in text.splitlines() if l.strip()]
    info = {}
    for c in cards:
        faces = c.get("card_faces") or [c]
        cost = c.get("mana_cost") or "".join(f.get("mana_cost", "") for f in faces)
        txt = "\n".join(f.get("oracle_text", "") for f in faces).lower()
        tl = (c.get("type_line") or "").lower()
        roles = {k for k, rx in ROLE.items() if rx.search(txt)}
        info[c["oracle_id"]] = {
            "cols": set(re.findall(r"[WUBRG]", cost)), "cmc": c.get("cmc") or 0, "land": "land" in tl.split("//")[0],
            "artifact": "artifact" in tl, "creature": "creature" in tl, "basic": "basic" in tl,
            "roles": roles, "mana": bool(MANA.search(txt)),
        }
    return info


# ----------------------------------------------------------------------------------------- labels

def label(main, card, name):
    """(colours, plan) for one deck's main deck (card indices, basics removed)."""
    pips = Counter()
    art = crea = spells = fatties = dorks = fast = 0
    cmc = 0.0
    f = Counter()
    for x in main:
        c = card(x)
        if not c or c["land"]:
            continue
        spells += 1
        cmc += c["cmc"]
        pips.update(c["cols"])
        art += c["artifact"]
        if c["creature"]:
            crea += 1
            fatties += c["cmc"] >= 6
            dorks += c["mana"] and c["cmc"] <= 3
        elif c["mana"] and c["cmc"] <= 1:
            fast += 1
        f.update(c["roles"])
    if spells < 12:
        return None
    total = sum(pips.values()) or 1
    main_cols = [k for k, v in pips.most_common() if v / total >= 0.2][:2]
    colours = "C" if not main_cols else ("mono " + main_cols[0] if len(main_cols) == 1
                                          else "".join(sorted(main_cols, key="WUBRG".index)))
    avg = cmc / spells
    if f["storm"] >= 1 and f["ritual"] + fast >= 3:
        plan = "Storm"
    elif f["reanimate"] >= 2 and fatties >= 1:
        plan = "Reanimator"
    elif f["cheat"] >= 1 and fatties >= 1:
        plan = "Sneak / cheat"
    elif art >= 9 and f["artifact_payoff"] >= 2:
        plan = "Artifacts"
    elif f["flicker"] >= 2:
        plan = "Blink"
    elif dorks + f["ramp"] >= 7 and "G" in main_cols:
        plan = "Ramp"
    elif crea >= 12 and avg <= 2.5:
        plan = "Aggro"
    elif f["counter"] + f["removal"] >= 8 and crea <= 10:
        plan = "Control"
    elif "U" in main_cols and f["counter"] >= 4 and 6 <= crea <= 11 and avg <= 2.6:
        plan = "Tempo"
    else:
        plan = "Midrange"
    return colours, plan


# ----------------------------------------------------------------------------------------- main

def build(out_path: str, max_files: int | None = None, workers: int = 16, force: bool = False):
    started = time.time()
    deck_keys = [k for k in list_keys("export/decks/") if k[0].endswith(".json")]
    stamp = max(k[2] for k in deck_keys)
    if os.path.exists(out_path) and not force:
        try:
            prev = json.load(open(out_path))
            if prev.get("source", {}).get("export_updated") == stamp:
                log("export unchanged since last build", stamp, "- nothing to do")
                return False
        except Exception:
            pass
    deck_keys.sort(key=lambda k: int(re.search(r"(\d+)\.json$", k[0]).group(1)))
    if max_files:
        step = max(1, len(deck_keys) // max_files)
        deck_keys = deck_keys[::step][:max_files]
    log(f"{len(deck_keys)} deck files, {sum(k[1] for k in deck_keys) / 1e9:.2f} GB")

    dict_ = get_json(f"{BUCKET}/export/simpleCardDict.json")
    idx_map = get_json(f"{BUCKET}/export/indexToOracleMap.json")
    log("card dictionary", len(dict_))
    info = load_scryfall()
    log("scryfall cards", len(info))

    n_idx = max(int(i) for i in idx_map) + 1
    oracle = [None] * n_idx
    for i, o in idx_map.items():
        oracle[int(i)] = o
    names = [(dict_.get(o) or {}).get("name") if o else None for o in oracle]
    elo = np.array([(dict_.get(o) or {}).get("elo") or 0 for o in oracle], dtype=np.float32) if n_idx else np.zeros(0)
    card = lambda x: info.get(oracle[x]) if 0 <= x < n_idx and oracle[x] else None
    power_idx = {i for i, n in enumerate(names) if n in POWER}
    basic_idx = {i for i in range(n_idx) if (card(i) or {}).get("basic")}

    # Cubes: card lists for the powered ones (decks that can't be matched fall back to their own pools).
    cubes = get_json(f"{BUCKET}/export/cubes.json")
    cube_cards, known_cubes = {}, set()
    for c in cubes:
        known_cubes.add(c["id"])
        cards = c.get("cards") or []
        if sum(1 for x in cards if x in power_idx) >= MIN_POWER_IN_CUBE:
            cube_cards[c["id"]] = np.unique(np.array([x for x in cards if x not in basic_idx], dtype=np.int32))
    del cubes
    log("powered cubes in cubes.json", len(cube_cards))

    # Decks (downloaded in parallel). Keep only decks from powered cubes.
    decks = []                     # (cube, main array, weight)
    fallback_pool = defaultdict(set)
    seen_files = 0

    def fetch(key):
        try:
            return get_json(f"{BUCKET}/{key}")
        except Exception as exc:
            log("skip", key, exc)
            return []

    with ThreadPoolExecutor(workers) as pool:
        for arr in pool.map(fetch, [k[0] for k in deck_keys]):
            seen_files += 1
            for d in arr:
                basics = set(d.get("basics") or []) | basic_idx
                main = [x for x in d.get("mainboard") or [] if x not in basics and 0 <= x < n_idx]
                side = [x for x in d.get("sideboard") or [] if 0 <= x < n_idx]
                cube = d.get("cube")
                if cube not in cube_cards:
                    if cube in known_cubes:
                        continue            # a listed cube without enough power
                    if any(x in power_idx for x in main) or any(x in power_idx for x in side):
                        fallback_pool[cube].update(main)
                        fallback_pool[cube].update(side)
                    else:
                        continue
                if len(main) < 20:
                    continue
                decks.append((cube, np.unique(np.array(main, dtype=np.int32))))
            if seen_files % 250 == 0:
                log(f"{seen_files}/{len(deck_keys)} files, {len(decks)} powered decks")
    for cube, cards in fallback_pool.items():
        if sum(1 for x in cards if x in power_idx) >= 1:
            cube_cards[cube] = np.unique(np.array([x for x in cards if x not in basic_idx], dtype=np.int32))
    decks = [d for d in decks if d[0] in cube_cards]
    log("powered decks", len(decks), "cubes", len(cube_cards))

    # Labels and weights (stronger decks count more).
    labels, weights = [], np.zeros(len(decks), dtype=np.float32)
    for i, (cube, main) in enumerate(decks):
        labels.append(label(main.tolist(), card, names))
        avg = float(elo[main].mean()) if len(main) else 0
        weights[i] = min(2.0, max(0.2, (avg - 1350) / 100))
    keep = [i for i, L in enumerate(labels) if L]

    # Card universe for the matrices: cards played in a decent number of powered decks.
    play = Counter()
    for i in keep:
        play.update(decks[i][1].tolist())
    min_play = max(150, len(keep) // 2500)          # ~1,100 decks on the full export: no obscure cards
    core = sorted(x for x, n in play.items() if n >= min_play and names[x])
    col = {x: j for j, x in enumerate(core)}
    K = len(core)
    cube_ids = sorted({decks[i][0] for i in keep})
    crow = {c: j for j, c in enumerate(cube_ids)}
    log(f"core cards {K}, cubes {len(cube_ids)}")

    # avail[cube, card] = 1 when the cube had the card; used[cube, card] = weighted decks that played it.
    avail = np.zeros((len(cube_ids), K), dtype=np.float32)
    for c, j in crow.items():
        cols_ = [col[x] for x in cube_cards[c].tolist() if x in col]
        avail[j, cols_] = 1
    deck_w_per_cube = np.zeros(len(cube_ids), dtype=np.float32)

    # ---- archetypes
    groups = defaultdict(list)
    for i in keep:
        colours, plan = labels[i]
        groups[plan].append(i)
        groups[f"{colours} {plan}"].append(i)

    def rates(idx_list):
        used = np.zeros(K, dtype=np.float64)
        seen = np.zeros(K, dtype=np.float64)
        per_cube = defaultdict(float)
        for i in idx_list:
            c, main = decks[i]
            w = weights[i]
            per_cube[c] += w
            cols_ = [col[x] for x in main.tolist() if x in col]
            used[cols_] += w
        for c, w in per_cube.items():
            seen += avail[crow[c]] * w
        return used, seen

    all_used, all_seen = rates(keep)
    base = np.divide(all_used, all_seen, out=np.zeros(K), where=all_seen > 0)
    archetypes = {}
    for key, idx_list in groups.items():
        if len(idx_list) < 300 or key.startswith("C "):
            continue
        used, seen = rates(idx_list)
        total_w = float(sum(weights[i] for i in idx_list))
        rate = np.divide(used, seen, out=np.zeros(K), where=seen > 0)
        lift = np.divide(rate, base, out=np.zeros(K), where=base > 0)
        ok = (seen >= 0.05 * total_w) & (used >= 5)
        score = np.where(ok, rate * np.sqrt(np.maximum(lift, 0)), -1)
        top = [j for j in np.argsort(-score)[:40] if score[j] > 0]
        archetypes[key] = {"decks": len(idx_list),
                           "cards": [[names[core[j]], round(100 * float(rate[j]), 1), round(float(lift[j]), 2)] for j in top]}
    log("archetypes", len(archetypes))

    # ---- synergy: lift of B given A, counting only decks whose cube had B.
    #   P(B | A, B available) = co[A,B] / avail_given_A[A,B];  base(B) = P(B | B available)
    co = np.zeros((K, K), dtype=np.float32)
    a_by_cube = np.zeros((len(cube_ids), K), dtype=np.float32)       # weighted decks with A, per cube
    for i in keep:
        c, main = decks[i]
        w = weights[i]
        js = np.array([col[x] for x in main.tolist() if x in col], dtype=np.int64)
        if len(js):
            co[np.ix_(js, js)] += w
            a_by_cube[crow[c], js] += w
    avail_given_a = a_by_cube.T @ avail                               # [A, B]
    # Shrink towards "no effect" so a pair needs plenty of shared decks before it counts: add M pseudo-decks
    # at B's base rate. Small samples then land near x1 instead of x60.
    M = 300.0
    b = base[None, :].astype(np.float32)
    p_b_given_a = (co + M * b) / (avail_given_a + M)
    lift = np.divide(p_b_given_a, b, out=np.zeros_like(co), where=b > 0)
    np.fill_diagonal(lift, 0)
    synergy = {}
    for a in range(K):
        row = lift[a]
        cand = np.where((row >= 1.4) & (co[a] >= 100))[0]
        if not len(cand):
            continue
        best = cand[np.argsort(-row[cand])][:12]
        synergy[names[core[a]]] = [[names[core[b]], round(float(row[b]), 2)] for b in best]
    log("synergy cards", len(synergy))

    out = {
        "source": {
            "name": "CubeCobra public data export",
            "url": "https://cubecobra.com",
            "export_updated": stamp,
            "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "deck_files": len(deck_keys),
            "powered_decks": len(keep),
            "powered_cubes": len(cube_ids),
        },
        "archetypes": dict(sorted(archetypes.items(), key=lambda kv: -kv[1]["decks"])),
        "synergy": dict(sorted(synergy.items())),
    }
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as fh:
        json.dump(out, fh, separators=(",", ":"), ensure_ascii=False)
    log(f"wrote {out_path} ({os.path.getsize(out_path) / 1e6:.2f} MB) in {(time.time() - started) / 60:.1f} min")
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="backend/data/cube_meta.json")
    ap.add_argument("--max-files", type=int, default=None, help="sample this many deck files (for a quick test)")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--force", action="store_true", help="rebuild even if the export hasn't changed")
    args = ap.parse_args()
    changed = build(args.out, args.max_files, args.workers, args.force)
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a") as fh:
            fh.write(f"changed={'true' if changed else 'false'}\n")
