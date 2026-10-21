"""Rebuild draftbot/pick_order.py from rotisserie draft sheets.

Usage: python scripts/build_pick_order.py sheet1.csv sheet2.csv ...
Each CSV is a draft sheet's "draft" tab exported as CSV (Google Sheets: File > Download > CSV, or
/gviz/tq?tqx=out:csv&sheet=draft): first row player names from the third column, then one row per round
(round number in the first column, picks from the third column), snake order (odd rounds left to right).
Only the averages are written: no player names.
"""
import csv
import json
import sys


def picks(path):
    rows = list(csv.reader(open(path, encoding="utf-8")))
    seats = len([x for x in rows[0][2:] if x.strip()])
    out = []
    for r in rows[1:]:
        if not r or not r[0].strip().isdigit():
            continue
        rnd = int(r[0])
        cards = r[2:2 + seats]
        for s in (range(seats) if rnd % 2 else range(seats - 1, -1, -1)):
            if s < len(cards) and cards[s].strip():
                out.append(cards[s].strip().split(" // ")[0])
    return seats, out


def main(paths):
    drafts = []
    for p in paths:
        seats, ps = picks(p)
        pos = {}
        for i, n in enumerate(ps):
            pos.setdefault(n, i / seats + 1)
        drafts.append((pos, len(ps) / seats))
    names = {n for pos, _ in drafts for n in pos}
    avg = {}
    for n in names:
        vals = [pos.get(n, rounds + 6) for pos, rounds in drafts]
        cnt = sum(1 for pos, _ in drafts if n in pos)
        a = round(sum(vals) / len(vals), 1)
        if cnt >= 2 or a <= 30:
            avg[n] = (a, cnt)
    body = "\n".join(f"    {json.dumps(n)}: {v}," for n, v in sorted(avg.items(), key=lambda kv: (kv[1][0], kv[0])))
    print("PICK_ORDER = {\n" + body + "\n}")


if __name__ == "__main__":
    main(sys.argv[1:])
