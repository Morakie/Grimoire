// Display names and colours for the bots' deck types (backend/draftbot/decktypes.py KEYS). A deck type the
// page doesn't know yet still shows, with a name made from its key.
export const DECK_NAMES = {
  tolarian: "Tolarian", workshop: "Workshop / Stax", artifacts: "Artifacts", welder: "Welder / Red artifacts",
  wildfire: "Wildfire", painter: "Painter", storm: "Storm", reanimator: "Reanimator", cheat: "Sneak / Show / Cheat",
  twin: "Twin", nadu: "Nadu", recursion: "Recursion / Pod", blink: "Blink", control: "Control", tempo: "UR Tempo",
  white_aggro: "White aggro", red_aggro: "Red aggro", gruul: "RG beats", pox: "Pox", domain: "Domain",
  ramp: "Green ramp", lands: "Lands",
};

export const DECK_COL = {
  tolarian: "#38bdf8", workshop: "#a8a29e", artifacts: "#f59e0b", welder: "#ea580c", wildfire: "#dc2626",
  painter: "#94a3b8", storm: "#e879f9", reanimator: "#8b5cf6", cheat: "#f43f5e", twin: "#fb7185", nadu: "#2dd4bf",
  recursion: "#65a30d", blink: "#facc15", control: "#60a5fa", tempo: "#818cf8", white_aggro: "#fde68a",
  red_aggro: "#fb923c", gruul: "#a3e635", pox: "#7c3aed", domain: "#14b8a6", ramp: "#22c55e", lands: "#84cc16",
};

export const deckName = (t) => DECK_NAMES[t] || t.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
export const deckCol = (t) => DECK_COL[t] || "#64748b";
