// =====================================================
// src/components/predictionCard.tsx
// Card PRO para uma previsão individual
// =====================================================

import React from "react";
import type { Prediction, DCClass } from "@/services/api";

function dcLabel(v?: DCClass) {
  return v === 0 ? "1X" : v === 1 ? "12" : v === 2 ? "X2" : "—";
}
function toPct(v?: number | null) {
  return typeof v === "number" ? `${Math.round(v * 100)}%` : "—";
}
function oddFmt(v?: number | null) {
  return typeof v === "number" ? v.toFixed(2) : "—";
}

export default function PredictionCard({ p }: { p: Prediction }) {
  const winner = p.predictions?.winner;
  const dc = p.predictions?.double_chance;
  const over25 = p.predictions?.over_2_5;
  const over15 = p.predictions?.over_1_5;
  const btts = p.predictions?.btts;

  const winnerLabel =
    winner?.class === 0 ? p.home_team : winner?.class === 1 ? "Empate" : winner?.class === 2 ? p.away_team : "—";

  return (
    <div className="p-5 rounded-2xl border border-gray-800 bg-gray-950 hover:border-green-500 transition flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
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

      {/* Teams */}
      <div className="flex items-center justify-center gap-3">
        {p.home_logo ? <img src={p.home_logo} alt="" className="w-7 h-7" /> : <div className="w-7 h-7" />}
        <div className="text-white font-semibold text-center">{p.home_team}</div>
        <div className="text-gray-500">vs</div>
        <div className="text-white font-semibold text-center">{p.away_team}</div>
        {p.away_logo ? <img src={p.away_logo} alt="" className="w-7 h-7" /> : <div className="w-7 h-7" />}
      </div>

      {/* Tips principais */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Winner</div>
          <div className="text-sm text-white">
            {winnerLabel} <span className="text-gray-400 ml-1">({toPct(winner?.confidence)})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Double Chance</div>
          <div className="text-sm text-white">
            {dcLabel(dc?.class)} <span className="text-gray-400 ml-1">({toPct(dc?.confidence)})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Over 2.5</div>
          <div className="text-sm text-white">
            {over25?.class ? "Sim" : "Não"} <span className="text-gray-400 ml-1">({toPct(over25?.confidence)})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Over 1.5</div>
          <div className="text-sm text-white">
            {over15?.class ? "Sim" : "Não"} <span className="text-gray-400 ml-1">({toPct(over15?.confidence)})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3 col-span-2">
          <div className="text-xs text-gray-400">BTTS</div>
          <div className="text-sm text-white">
            {btts?.class ? "Sim" : "Não"} <span className="text-gray-400 ml-1">({toPct(btts?.confidence)})</span>
          </div>
        </div>
      </div>

      {/* Odds lineadas */}
      {p.odds && (
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400 mb-2">Odds</div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <div>
              <div className="text-gray-400 text-xs mb-1">1X2</div>
              <div className="text-white">
                {oddFmt(p.odds?.winner?.home)} / {oddFmt(p.odds?.winner?.draw)} / {oddFmt(p.odds?.winner?.away)}
              </div>
            </div>
            <div>
              <div className="text-gray-400 text-xs mb-1">O/U 2.5</div>
              <div className="text-white">
                O {oddFmt(p.odds?.over_2_5?.over)} · U {oddFmt(p.odds?.over_2_5?.under)}
              </div>
            </div>
            <div>
              <div className="text-gray-400 text-xs mb-1">BTTS</div>
              <div className="text-white">
                Sim {oddFmt(p.odds?.btts?.yes)} · Não {oddFmt(p.odds?.btts?.no)}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Accordion: Correct Score + Top Scorers */}
      <details className="rounded-xl bg-gray-900 border border-gray-800 p-3">
        <summary className="cursor-pointer text-sm text-gray-200 select-none">
          Detalhes (Correct Score & Marcadores)
        </summary>
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <div className="text-xs text-gray-400 mb-1">Top-3 Correct Score</div>
            <ul className="text-sm text-white space-y-1">
              {p.correct_score_top3?.length
                ? p.correct_score_top3.slice(0, 3).map((cs, idx) => (
                    <li key={idx} className="flex justify-between">
                      <span>{cs.score}</span>
                      <span className="text-gray-400">
                        {Math.round(((cs.prob ?? 0) * 1000)) / 10}%
                      </span>
                    </li>
                  ))
                : <li className="text-gray-500">—</li>}
            </ul>
          </div>
          <div>
            <div className="text-xs text-gray-400 mb-1">Top Scorers (liga)</div>
            <ul className="text-sm text-white space-y-1">
              {p.top_scorers?.length
                ? p.top_scorers.slice(0, 5).map((sc, idx) => (
                    <li key={idx} className="flex justify-between">
                      <span>
                        {sc.player} <span className="text-gray-400">({sc.team})</span>
                      </span>
                      <span className="text-gray-400">{sc.goals} golos</span>
                    </li>
                  ))
                : <li className="text-gray-500">—</li>}
            </ul>
          </div>
        </div>
      </details>
    </div>
  );
}
