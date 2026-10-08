"""Commander legality and bracket estimate (pure logic, no server or network needed)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from commander import evaluate, valid_pair, is_mld, is_extra_turn, can_be_commander  # noqa: E402


def card(name, type_line="Instant", ci=(), text="", qty=1):
    return {"name": name, "type_line": type_line, "color_identity": list(ci), "oracle_text": text, "quantity": qty}


ATRAXA = card("Atraxa, Praetors' Voice", "Legendary Creature — Phyrexian Angel Horror", "WUBG", "Flying, vigilance")
KRARK = card("Krark, the Thumbless", "Legendary Creature — Goblin Wizard", "R", "Partner")
SAKASHIMA = card("Sakashima of a Thousand Faces", "Legendary Creature — Human Rogue", "U", "Partner")
WILSON = card("Wilson, Refined Grizzly", "Legendary Creature — Bear Warrior", "G", "Choose a Background")
BG = card("Raised by Giants", "Legendary Enchantment — Background", "G", "Commander creatures you own have base power...")
GRIZZ = card("Grizzled Bear", "Creature — Bear", "G")


def filler(n, ci="G"):
    return [card(f"Filler {i}", "Creature — Elf", ci) for i in range(n)]


def forests(n):
    return [card("Forest", "Basic Land — Forest", (), "", n)]


def test_legal_100_card_deck():
    r = evaluate([ATRAXA], filler(60) + forests(39), [], [])
    assert r["legal"], r["issues"]
    assert r["card_count"] == 100
    assert r["bracket"]["label"] == "1–2"


def test_size_identity_singleton_banned():
    cards = filler(50) + [card("Lightning Bolt", ci="R"), card("Sol Ring", "Artifact", (), "", 2), card("Black Lotus", "Artifact")]
    r = evaluate([ATRAXA], cards, [], ["Black Lotus"])
    kinds = {i["kind"] for i in r["issues"]}
    assert kinds == {"size", "identity", "singleton", "banned"}
    ident = next(i for i in r["issues"] if i["kind"] == "identity")
    assert ident["cards"] == ["Lightning Bolt"]


def test_any_number_of_copies_allowed():
    rats = card("Relentless Rats", "Creature — Rat", "B", "A deck can have any number of cards named Relentless Rats.", 30)
    r = evaluate([ATRAXA], [rats], [], [])
    assert not any(i["kind"] == "singleton" for i in r["issues"])


def test_commander_eligibility_and_pairs():
    assert can_be_commander(ATRAXA)
    assert not can_be_commander(GRIZZ)
    assert valid_pair(KRARK, SAKASHIMA)
    assert valid_pair(WILSON, BG)
    assert not valid_pair(ATRAXA, KRARK)
    r = evaluate([ATRAXA, KRARK], filler(98), [], [])
    assert any(i["kind"] == "commander" for i in r["issues"])
    r = evaluate([BG], filler(99), [], [])
    assert any(i["kind"] == "commander" for i in r["issues"])
    r = evaluate([], filler(100), [], [])
    assert any(i["kind"] == "commander" for i in r["issues"])


def test_partner_with():
    a = card("Pir, Imaginative Rascal", "Legendary Creature — Human", "G", "Partner with Toothy, Imaginary Friend (When this creature enters...)")
    b = card("Toothy, Imaginary Friend", "Legendary Creature — Illusion", "U", "Partner with Pir, Imaginative Rascal (When this creature enters...)")
    assert valid_pair(a, b)
    assert not valid_pair(a, KRARK)


def test_bracket_levels():
    gcs = ["Rhystic Study", "Cyclonic Rift", "Smothering Tithe", "Demonic Tutor"]
    deck = filler(95) + [card(n) for n in gcs]
    assert evaluate([ATRAXA], deck[:-1], gcs, [])["bracket"]["estimate"] == 3     # three Game Changers
    assert evaluate([ATRAXA], deck, gcs, [])["bracket"]["estimate"] == 4          # four
    combo = evaluate([ATRAXA], filler(99), [], [], combos=[["A", "B"]])
    assert combo["bracket"]["estimate"] == 3 and "early" in combo["bracket"]["reasons"][0]
    mld = evaluate([ATRAXA], filler(98) + [card("Armageddon", "Sorcery", "W", "Destroy all lands.")], [], [])
    assert mld["bracket"]["estimate"] == 4


def test_card_text_detection():
    assert is_mld(card("Ravages of War"))
    assert is_mld(card("Some Card", text="Each player sacrifices all lands they control."))
    assert not is_mld(card("Wrath of God", text="Destroy all creatures. They can't be regenerated."))
    assert is_extra_turn(card("Time Warp", text="Target player takes an extra turn after this one."))
    assert not is_extra_turn(card("Shock", text="Shock deals 2 damage to any target."))
