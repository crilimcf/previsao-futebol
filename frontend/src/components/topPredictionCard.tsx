"use client";

import Image from "next/image";

// -----------------------------
// Utils
// -----------------------------
type DCClass = 0 | 1 | 2;

const FALLBACK_SVG =
  "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='28' height='28'><rect width='100%' height='100%' fill='%23222'/></svg>";

function prob01(v?: number | null): number {
  if (typeof v !== "number" || !isFinite(v)) return 0;
  return v > 1 ? Math.max(0, Math.min(1, v / 100)) : Math.max(0, Math.min(1, v));
}
function pct(v?: number | null) {
  const p = prob01(v) * 100;
  if (!isFinite(p) || p <= 0) return "0%";
  if (p >= 99.9) return "≈100%";
  return `${Math.round(p)}%`;
}
const oddFmt = (v?: number | null) =>
  typeof v === "number" && isFinite(v) ? v.toFixed(2) : "—";

const dcLabel = (dc: DCClass | string | undefined) => {
  if (typeof dc === "string") return dc.toUpperCase();
  return dc === 0 ? "1X" : dc === 1 ? "12" : dc === 2 ? "X2" : "—";
};

const isValidOdd = (v?: number | null) =>
  typeof v === "number" && isFinite(v) && v >= 1.2 && v <= 100;

// Evita crash/TS error quando date pode vir undefined
function safeDate(val?: string | number | Date) {
  if (val === undefined || val === null) return new Date();
  const d = new Date(val as any);
  if (!isNaN(d.getTime())) return d;
  if (typeof val === "string") {
    const d2 = new Date(val.replace(" ", "T"));
    if (!isNaN(d2.getTime())) return d2;
  }
  return new Date();
}

// -----------------------------
// Tipos
// -----------------------------
export type TopPredictionCardProps = {
  league?: string;
  league_name?: string;
  country?: string;
  date?: string; // pode faltar -> safeDate trata
  home_team: string;
  away_team: string;
  home_logo?: string;
  away_logo?: string;
  odds_source?: "market" | "model"; // <— para decidir se mostramos OU 2.5
  predictions?: {
    winner?: { class: 0 | 1 | 2; prob?: number; confidence?: number };
    double_chance?: { class: DCClass; prob?: number; confidence?: number };
    over_2_5?: { class: 0 | 1; prob?: number; confidence?: number };
    over_1_5?: { class: 0 | 1; prob?: number; confidence?: number };
    btts?: { class: 0 | 1; prob?: number; confidence?: number };
    correct_score?: { best?: string; top3?: { score: string; prob: number }[] };
  };
  odds?: {
    winner?: { home?: number; draw?: number; away?: number };
    ["1x2"]?: { home?: number; draw?: number; away?: number };
    over_2_5?: { over?: number; under?: number };
    over_under?: Record<string, { over?: number; under?: number }>;
    btts?: { yes?: number; no?: number };
  };
  // opcionalmente pode vir algo como "score" agregado
  correct_score_top3?: { score: string; prob: number }[];
};

export default function TopPredictionCard(props: TopPredictionCardProps) {
  const {
    league,
    league_name,
    country,
    date,
    home_team,
    away_team,
    home_logo,
    away_logo,
    predictions,
    odds,
    correct_score_top3,
    odds_source,
  } = props;

  function deriveWinnerLabel(pred: any) {
    try {
      const w = pred?.winner;
      if (w) {
        if (w.probs && typeof w.probs === "object") {
          const probs = w.probs as Record<string, number>;
          const keys = Object.keys(probs).filter((k) => k);
          if (keys.length) {
            const best = keys.reduce((a, b) => (probs[b] > probs[a] ? b : a), keys[0]);
            if (best === "home") return home_team;
            if (best === "draw") return "Empate";
            if (best === "away") return away_team;
          }
        }
        const label = (w.label || w.side || w.winner || "").toString().toLowerCase();
        if (label === "home") return home_team;
        if (label === "draw" || label === "empate") return "Empate";
        if (label === "away") return away_team;
        const cls = typeof w.class === "number" ? w.class : parseInt(w.class, 10);
        if (cls === 0) return home_team;
        if (cls === 1) return "Empate";
        if (cls === 2) return away_team;
      }
    } catch (e) {}
    return "—";
  }

  const winnerLabel = deriveWinnerLabel(predictions);

  const odds1x2 = odds?.winner ?? odds?.["1x2"] ?? {};
  const oddsOU25 = odds?.over_2_5 ?? (odds?.over_under?.["2.5"] ?? {});
  const oddsBTTS = odds?.btts ?? {};

  const show1x2 =
    isValidOdd(odds1x2?.home) && isValidOdd(odds1x2?.draw) && isValidOdd(odds1x2?.away);

  // Só mostra OU 2.5 se vier de mercado E for válido
  const showOU25 =
    odds_source === "market" &&
    isValidOdd(oddsOU25?.over) &&
    isValidOdd(oddsOU25?.under);

  const showBTTS =
    isValidOdd(oddsBTTS?.yes) && isValidOdd(oddsBTTS?.no);

  const showAnyOdds = show1x2 || showOU25 || showBTTS;

  const bestCS =
    correct_score_top3?.[0]?.score ??
    predictions?.correct_score?.top3?.[0]?.score ??
    predictions?.correct_score?.best ??
    "—";

  const pWinner = predictions?.winner?.confidence ?? predictions?.winner?.prob;
  const pDC = predictions?.double_chance?.confidence ?? predictions?.double_chance?.prob;
  const pO25 = predictions?.over_2_5?.confidence ?? predictions?.over_2_5?.prob;
  const pO15 = predictions?.over_1_5?.confidence ?? predictions?.over_1_5?.prob;
  const pBTTS = predictions?.btts?.confidence ?? predictions?.btts?.prob;

  return (
    <div className="p-5 rounded-2xl border border-gray-800 bg-gray-950 hover:border-emerald-500 transition flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-400">
          {league_name || league || "Liga"} {country ? `(${country})` : ""}
        </div>
        <div className="text-xs text-gray-500">
          {safeDate(date).toLocaleString("pt-PT", {
            day: "2-digit",
            month: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>
      </div>

      {/* Teams */}
      <div className="flex items-center justify-center gap-3">
        <Image
          src={home_logo || FALLBACK_SVG}
          alt={home_team || "Home"}
          width={28}
          height={28}
          className="w-7 h-7"
          unoptimized
        />
        <div className="text-white font-semibold text-center">{home_team}</div>
        <div className="text-gray-500">vs</div>
        <div className="text-white font-semibold text-center">{away_team}</div>
        <Image
          src={away_logo || FALLBACK_SVG}
          alt={away_team || "Away"}
          width={28}
          height={28}
          className="w-7 h-7"
          unoptimized
        />
      </div>

      {/* Correct score */}
      <div className="flex items-center justify-center gap-2">
        <span className="badge">Correct Score</span>
        <span className="text-sm text-white">{bestCS}</span>
      </div>

      {/* Destaques rápidos */}
      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Winner</div>
          <div className="text-sm text-white">
            {winnerLabel} <span className="text-gray-400 ml-1">({pct(pWinner)})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Double Chance</div>
          <div className="text-sm text-white">
            {dcLabel(predictions?.double_chance?.class)}{" "}
            <span className="text-gray-400 ml-1">({pct(pDC)})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Over 2.5</div>
          <div className="text-sm text-white">
            {predictions?.over_2_5?.class ? "Sim" : "Não"}{" "}
            <span className="text-gray-400 ml-1">({pct(pO25)})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400">Over 1.5</div>
          <div className="text-sm text-white">
            {predictions?.over_1_5?.class ? "Sim" : "Não"}{" "}
            <span className="text-gray-400 ml-1">({pct(pO15)})</span>
          </div>
        </div>

        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3 col-span-2">
          <div className="text-xs text-gray-400">BTTS</div>
          <div className="text-sm text-white">
            {predictions?.btts?.class ? "Sim" : "Não"}{" "}
            <span className="text-gray-400 ml-1">({pct(pBTTS)})</span>
          </div>
        </div>
      </div>

      {/* Odds (mostra só sub-blocos válidos) */}
      {showAnyOdds && (
        <div className="rounded-xl bg-gray-900 border border-gray-800 p-3">
          <div className="text-xs text-gray-400 mb-2">
            Odds {odds_source === "market" ? "(mercado)" : "(modelo)"}
          </div>
          <div className="grid grid-cols-3 gap-2 text-sm">
            {show1x2 && (
              <div>
                <div className="text-gray-400 text-xs mb-1">1X2</div>
                <div className="text-white">
                  {oddFmt(odds1x2?.home)} / {oddFmt(odds1x2?.draw)} / {oddFmt(odds1x2?.away)}
                </div>
              </div>
            )}
            {showOU25 && (
              <div>
                <div className="text-gray-400 text-xs mb-1">O/U 2.5</div>
                <div className="text-white">
                  O {oddFmt(oddsOU25?.over)} · U {oddFmt(oddsOU25?.under)}
                </div>
              </div>
            )}
            {showBTTS && (
              <div>
                <div className="text-gray-400 text-xs mb-1">BTTS</div>
                <div className="text-white">
                  Sim {oddFmt(oddsBTTS?.yes)} · Não {oddFmt(oddsBTTS?.no)}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
