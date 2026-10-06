import React from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie } from "recharts";
import { computeAnalytics, MANA_COLORS } from "@/lib/mtg";

function StatWidget({ label, value, testid }) {
  return (
    <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 flex flex-col" data-testid={testid}>
      <span className="text-[11px] uppercase tracking-wide text-slate-500">{label}</span>
      <span className="text-xl font-display font-bold text-slate-100 mt-1">{value}</span>
    </div>
  );
}

const CurveTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-100 shadow-xl">
      CMC {label}: <span className="font-bold text-amber-400">{payload[0].value}</span>
    </div>
  );
};

export default function DeckStats({ cards }) {
  const { manaCurve, colorDist, typeBreakdown, total, avgCmc } = computeAnalytics(cards);
  const maxCurve = Math.max(...manaCurve.map((d) => d.count), 1);

  return (
    <div className="space-y-5" data-testid="deck-stats">
      <div className="grid grid-cols-2 gap-3">
        <StatWidget label="Total Cards" value={total} testid="stat-total" />
        <StatWidget label="Avg. Mana Value" value={avgCmc.toFixed(2)} testid="stat-avgcmc" />
      </div>

      <div>
        <h4 className="text-xs uppercase tracking-wide text-slate-400 mb-2 font-semibold">Mana Curve</h4>
        <div className="bg-slate-950 border border-slate-800 rounded-lg p-2 h-40">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={manaCurve} margin={{ top: 8, right: 4, left: -24, bottom: 0 }}>
              <XAxis dataKey="cmc" tick={{ fill: "#94a3b8", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "#64748b", fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip content={<CurveTooltip />} cursor={{ fill: "rgba(251,191,36,0.08)" }} />
              <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                {manaCurve.map((d, i) => (
                  <Cell key={i} fill={d.count === maxCurve && maxCurve > 0 ? "#fbbf24" : "#64748b"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div>
        <h4 className="text-xs uppercase tracking-wide text-slate-400 mb-2 font-semibold">Color Distribution</h4>
        <div className="bg-slate-950 border border-slate-800 rounded-lg p-2 flex items-center">
          <div className="h-32 w-32 shrink-0">
            {colorDist.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={colorDist} dataKey="value" innerRadius={34} outerRadius={56} paddingAngle={2} stroke="none">
                    {colorDist.map((d) => <Cell key={d.key} fill={d.color} />)}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-xs text-slate-600">No cards</div>
            )}
          </div>
          <div className="flex-1 space-y-1 pl-2">
            {colorDist.map((d) => (
              <div key={d.key} className="flex items-center gap-2 text-xs">
                <span className="w-3 h-3 rounded-full" style={{ background: d.color }} />
                <span className="text-slate-300 flex-1">{d.name}</span>
                <span className="text-slate-400 tabular-nums">{d.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div>
        <h4 className="text-xs uppercase tracking-wide text-slate-400 mb-2 font-semibold">Card Types</h4>
        <div className="bg-slate-950 border border-slate-800 rounded-lg divide-y divide-slate-800/60">
          {typeBreakdown.length === 0 && <div className="p-3 text-xs text-slate-600">No cards yet</div>}
          {typeBreakdown.map((t) => (
            <div key={t.name} className="flex items-center justify-between px-3 py-1.5 text-sm">
              <span className="text-slate-300">{t.name}</span>
              <span className="text-amber-400 font-semibold tabular-nums">{t.count}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
