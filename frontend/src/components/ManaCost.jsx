import React from "react";
import { parseMana, symbolStyle, symbolLabel } from "@/lib/mtg";

export function ManaCost({ cost, size = 16, className = "" }) {
  const symbols = parseMana(cost);
  if (!symbols.length) return null;
  return (
    <span className={`inline-flex items-center gap-[2px] ${className}`} data-testid="mana-cost">
      {symbols.map((sym, i) => {
        const style = symbolStyle(sym);
        return (
          <span
            key={i}
            style={{
              background: style.bg,
              color: style.text,
              width: size,
              height: size,
              fontSize: size * 0.58,
            }}
            className="inline-flex items-center justify-center rounded-full font-bold leading-none shadow-sm"
          >
            {symbolLabel(sym)}
          </span>
        );
      })}
    </span>
  );
}
