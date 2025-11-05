// =====================================================
// src/components/topPredictionCard.tsx
// Card destaque (primeira previsão)
// =====================================================

"use client";

import React from "react";
import Image from "next/image";
import type { Prediction } from "@/services/api";

type DCClass = 0 | 1 | 2;

function dcLabel(v?: DCClass) {
  return v === 0 ? "1X" : v === 1 ? "12" : v === 2 ? "X2" : "—";
}
function toPct(v?: number | null) {
  return typeof v === "number" ? `${Math.round(v * 100)}%` : "—";
}

const FALLBACK_SVG_32 =
  "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32'><rect width='100%' height='100%' fill='%23222'/></svg>";

export default function TopPredictionCard({ p }: { p: Prediction }) {
  const winnerClass = p.predictions?.winner?.class;
  const winnerLabel =
    winnerClass === 0 ? p.home_team :
    winnerClass === 1 ? "Empate" :
    winnerClass === 2 ? p.away_team : "—";

  // aceitar 'confidence' ou 'prob'
  const prob = (x?: { confidence?: number; prob?: number }) =>
    x?.confidence ?? x?.prob;

  const tips = [
    { label: "Winner", value: winnerLabel, conf: prob(p.predictions?.winner) },
    { label: "Double Chance", value: dcLabel(p.predictions?.double_chance?.class as DCClass), conf: prob(p.predictions?.double_chance) },
    { label: "Over 2.5", value: p.predictions?.over_2_5?.class ? "Sim" : "Não", conf: prob(p.predictions?.over_2_5) },
    { label: "Over 1.5", value: p.predictions?.over_1_5?.class ? "Sim" : "Não", conf: prob(p.predictions?.over_1_5) },
    { label: "BTTS", value: p.predictions?.btts?.class ? "Sim" : "Não", conf: prob(p.predictions?.btts) },
  ];

  const bestCS =
    (p as any)?.correct_score_top3?.[0]?.score ??
    (p as any)?.predictions?.correct_score?.best ??
    "—";

  return (
    <div className="rounded-2xl border border-emerald-600 bg-gray-950 p-6 shadow-lg">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm text-gray-400">
          {(p as any).league_name ?? p.league ?? "Liga"} {p.country ? `(${p.country})` : ""}
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
        <Image
          src={p.home_logo || FALLBACK_SVG_32}
          alt={p.home_team || "Home"}
          width={32}
          height={32}
        />
        <div className="text-xl font-bold text-white text-center">{p.home_team}</div>
        <div className="text-gray-500">vs</div>
        <div className="text-xl font-bold text-white text-center">{p.away_team}</div>
        <Image
          src={p.away_logo || FALLBACK_SVG_32}
          alt={p.away_team || "Away"}
          width={32}
          height={32}
        />
      </div>

      {/* Correct score destaque */}
      <div className="flex items-center justify-center gap-2 mb-3">
        <span className="badge">Correct Score</span>
        <span className="text-sm text-white">{bestCS}</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {tips.map((t) => (
          <div key={t.label} className="rounded-xl bg-white/5 border border-white/10 p-3">
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
