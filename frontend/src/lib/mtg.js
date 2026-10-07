// MTG helpers: mana parsing, colors, deck analytics

export const MANA_COLORS = {
  W: { bg: "#f6f0d8", text: "#1c1917", label: "White" },
  U: { bg: "#2f7fd1", text: "#f8fafc", label: "Blue" },
  B: { bg: "#4b3a63", text: "#f8fafc", label: "Black" },
  R: { bg: "#e05a47", text: "#f8fafc", label: "Red" },
  G: { bg: "#3f9b52", text: "#f8fafc", label: "Green" },
  C: { bg: "#9aa7b4", text: "#0f172a", label: "Colorless" },
};

const COLOR_ORDER = ["W", "U", "B", "R", "G", "C"];

export function parseMana(manaCost) {
  if (!manaCost) return [];
  const matches = manaCost.match(/\{([^}]+)\}/g) || [];
  return matches.map((m) => m.slice(1, -1));
}

export function symbolStyle(sym) {
  const s = sym.replace("/P", "").split("/")[0];
  if (MANA_COLORS[s]) return MANA_COLORS[s];
  if (s === "T") return { bg: "#334155", text: "#f8fafc", label: "Tap" };
  return { bg: "#cbd5e1", text: "#1e293b", label: "Generic" };
}

export function symbolLabel(sym) {
  if (sym.includes("/")) return sym.replace("/", "");
  if (sym === "T") return "T";
  return sym;
}

export function isBasicLand(card) {
  return (card.type_line || "").toLowerCase().includes("basic land");
}

export function maxCopies(card, format) {
  if (isBasicLand(card)) return 99;
  if (format === "kitchen") return 99;
  if (format === "commander" || format === "brawl") return 1;
  return 4;
}

export function primaryType(typeLine) {
  const t = (typeLine || "").toLowerCase();
  if (t.includes("land")) return "Lands";
  if (t.includes("creature")) return "Creatures";
  if (t.includes("planeswalker")) return "Planeswalkers";
  if (t.includes("instant")) return "Instants";
  if (t.includes("sorcery")) return "Sorceries";
  if (t.includes("artifact")) return "Artifacts";
  if (t.includes("enchantment")) return "Enchantments";
  if (t.includes("battle")) return "Battles";
  return "Other";
}

export function totalCount(cards) {
  return cards.reduce((n, c) => n + (c.quantity || 0), 0);
}

export function computeAnalytics(cards) {
  const nonLand = cards.filter((c) => !(c.type_line || "").toLowerCase().includes("land"));
  // Mana curve buckets 0..7+
  const curve = [0, 0, 0, 0, 0, 0, 0, 0];
  nonLand.forEach((c) => {
    const bucket = Math.min(7, Math.floor(c.cmc || 0));
    curve[bucket] += c.quantity || 0;
  });
  const manaCurve = curve.map((count, i) => ({ cmc: i === 7 ? "7+" : String(i), count }));

  // Color pips distribution
  const colorCounts = { W: 0, U: 0, B: 0, R: 0, G: 0, C: 0 };
  cards.forEach((c) => {
    const ids = c.color_identity && c.color_identity.length ? c.color_identity : [];
    if (ids.length === 0) colorCounts.C += c.quantity || 0;
    else ids.forEach((col) => { if (colorCounts[col] !== undefined) colorCounts[col] += c.quantity || 0; });
  });
  const colorDist = COLOR_ORDER.map((k) => ({
    key: k,
    name: MANA_COLORS[k].label,
    value: colorCounts[k],
    color: MANA_COLORS[k].bg,
  })).filter((d) => d.value > 0);

  // Type breakdown
  const types = {};
  cards.forEach((c) => {
    const t = primaryType(c.type_line);
    types[t] = (types[t] || 0) + (c.quantity || 0);
  });
  const typeBreakdown = Object.entries(types).map(([name, count]) => ({ name, count })).sort((a, b) => b.count - a.count);

  const total = totalCount(cards);
  const nonLandCount = totalCount(nonLand);
  const totalCmc = nonLand.reduce((s, c) => s + (c.cmc || 0) * (c.quantity || 0), 0);
  const avgCmc = nonLandCount ? (totalCmc / nonLandCount) : 0;

  return { manaCurve, colorDist, typeBreakdown, total, avgCmc };
}

export const FORMATS = [
  { value: "standard", label: "Standard" },
  { value: "commander", label: "Commander / EDH" },
  { value: "modern", label: "Modern" },
  { value: "pioneer", label: "Pioneer" },
  { value: "pauper", label: "Pauper" },
  { value: "legacy", label: "Legacy" },
  { value: "vintage", label: "Vintage" },
  { value: "kitchen", label: "Kitchen Magic (no rules)" },
];

export function formatLabel(value) {
  return (FORMATS.find((f) => f.value === value) || {}).label || value;
}

// ---------- Board view: grouping / sorting ----------

export function colorGroup(card) {
  const ci = card.color_identity && card.color_identity.length ? card.color_identity : [];
  if (ci.length === 0) return "Colorless";
  if (ci.length > 1) return "Multicolor";
  return (MANA_COLORS[ci[0]] || {}).label || "Colorless";
}

export function groupKeyFor(card, mode) {
  if (card.group_overrides && card.group_overrides[mode]) return card.group_overrides[mode];
  if (mode === "type") return primaryType(card.type_line);
  if (mode === "cmc") {
    if ((card.type_line || "").toLowerCase().includes("land")) return "Lands";
    const b = Math.min(7, Math.floor(card.cmc || 0));
    return b === 7 ? "7+" : String(b);
  }
  if (mode === "color") return colorGroup(card);
  return "all";
}

export const GROUP_ORDER = {
  type: ["Creatures", "Planeswalkers", "Instants", "Sorceries", "Artifacts", "Enchantments", "Battles", "Lands", "Other"],
  cmc: ["0", "1", "2", "3", "4", "5", "6", "7+", "Lands"],
  color: ["White", "Blue", "Black", "Red", "Green", "Multicolor", "Colorless"],
  custom: ["all"],
};

export function sortCards(cards, sortMode) {
  if (sortMode === "name") return [...cards].sort((a, b) => a.name.localeCompare(b.name));
  if (sortMode === "cmc") return [...cards].sort((a, b) => (a.cmc - b.cmc) || a.name.localeCompare(b.name));
  return cards; // manual = stored array order
}

export const VIEW_OPTIONS = [
  { value: "text", label: "Text" },
  { value: "grid", label: "Visual Grid" },
];
export const GROUP_OPTIONS = [
  { value: "type", label: "Type" },
  { value: "cmc", label: "Mana Value" },
  { value: "color", label: "Color" },
  { value: "custom", label: "Custom" },
];
export const SORT_OPTIONS = [
  { value: "manual", label: "Manual" },
  { value: "name", label: "Name" },
  { value: "cmc", label: "Mana Value" },
];
