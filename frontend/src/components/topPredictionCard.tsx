// =====================================================
// src/components/topPredictionCard.tsx
// Card destaque (primeira previsão)
// =====================================================

import React from "react";
import type { Prediction, DCClass } from "@/services/api";

function dcLabel(v?: DCClass) {
  return v === 0 ? "1X" : v === 1 ? "12" : v === 2 ? "X2" : "—";
}
function toPct(v?: number | null) {
  return typeof v === "number" ? `${Math.round(v * 100)}%` : "—";
}

export default function TopPredictionCard({ p }: { p: Prediction }) {
  const tips = [
    { label: "Winner", value: p.predictions.winner?.class === 0 ? p.home_team : p.predictions.winner?.class === 1 ? "Empate" : p.away_team, conf: p.predictions.winner?.confidence },
    { label: "Double Chance", value: dcLabel(p.predictions.double_chance?.class), conf: p.predictions.double_chance?.confidence },
    { label: "Over 2.5", value: p.predictions.over_2_5?.class ? "Sim" : "Não", conf: p.predictions.over_2_5?.confidence },
    { label: "Over 1.5", value: p.predictions.over_1_5?.class ? "Sim" : "Não", conf: p.predictions.over_1_5?.confidence },
    { label: "BTTS", value: p.predictions.btts?.class ? "Sim" : "Não", conf: p.predictions.btts?.confidence },
  ];

  return (
    <div className="rounded-2xl border border-green-600 bg-gray-950 p-6 shadow-lg">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm text-gray-400">
          {p.league} {p.country ? `(${p.country})` : ""}
        </div>
        <div className="text-xs text-gray-500">
          {new Date(p.date).toLocaleString("pt-PT", {
            day: "2-digit",
            month: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>
      </div>

      <div className="flex items-center justify-center gap-4 mb-3">
        {p.home_logo ? <img src={p.home_logo} alt="" className="w-8 h-8" /> : <div className="w-8 h-8" />}
        <div className="text-xl font-bold text-white text-center">{p.home_team}</div>
        <div className="text-gray-500">vs</div>
        <div className="text-xl font-bold text-white text-center">{p.away_team}</div>
        {p.away_logo ? <img src={p.away_logo} alt="" className="w-8 h-8" /> : <div className="w-8 h-8" />}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {tips.map((t) => (
          <div key={t.label} className="rounded-xl bg-gray-900 border border-gray-800 p-3">
            <div className="text-xs text-gray-400">{t.label}</div>
            <div className="text-sm text-white">
              {t.value} <span className="text-gray-400 ml-1">({toPct(t.conf)})</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
