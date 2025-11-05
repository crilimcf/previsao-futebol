"use client";

export type PredictionField = {
  class: number | string;          // 0/1/2 ou "1X"/"12"/"X2" no caso de DC
  confidence?: number;             // 0..1
  prob?: number;                   // 0..1 (backend novo)
};

export type PredictionBlock = {
  winner: PredictionField;
  over_2_5: PredictionField;
  over_1_5: PredictionField;
  double_chance: PredictionField;
  btts: PredictionField;
};

export type Match = {
  match_id: string | number;
  home_team: string;
  away_team: string;
  predictions: PredictionBlock;
};

const FIELDS: Array<{ key: keyof PredictionBlock; label: string }> = [
  { key: "winner", label: "Winner" },
  { key: "double_chance", label: "Double Chance" },
  { key: "over_2_5", label: "Over 2.5" },
  { key: "over_1_5", label: "Over 1.5" },
  { key: "btts", label: "BTTS" },
];

const pct = (f?: PredictionField) => {
  const v = f?.confidence ?? f?.prob ?? 0;
  return `${Math.round((Number.isFinite(v) ? v : 0) * 100)}%`;
};

const dcLabel = (v: number | string) => {
  if (typeof v === "string") return v.toUpperCase(); // já vem "1X" | "12" | "X2"
  if (v === 0) return "1X";
  if (v === 1) return "12";
  if (v === 2) return "X2";
  return "-";
};

const winnerLabel = (v: number, home: string, away: string) =>
  v === 0 ? home : v === 1 ? "Empate" : away;

const boolLabel = (v: number) => (v === 1 ? "Sim" : "Não");

export function PredictionItem({ match }: { match: Match }) {
  const { home_team, away_team, predictions } = match;

  return (
    <li className="mb-3 rounded-xl border border-gray-800/70 bg-gray-900/50 p-3">
      <strong className="text-sm text-white">
        {home_team} <span className="text-gray-500">vs</span> {away_team}
      </strong>
      <ul className="ml-4 mt-2 list-disc text-sm text-gray-200 space-y-1">
        {FIELDS.map(({ key, label }) => {
          const field = predictions[key];
          let txt: string;

          switch (key) {
            case "winner":
              txt = winnerLabel(Number(field.class), home_team, away_team);
              break;
            case "double_chance":
              txt = dcLabel(field.class);
              break;
            case "btts":
            case "over_2_5":
            case "over_1_5":
              txt = boolLabel(Number(field.class));
              break;
            default:
              txt = String(field.class);
          }

          return (
            <li key={key}>
              {label}: {txt}{" "}
              <span className="text-gray-400">({pct(field)})</span>
            </li>
          );
        })}
      </ul>
    </li>
  );
}
