"use client";
import { useEffect, useState } from "react";
import Header from "@/components/header";
import InfoCard from "@/components/infoCards";
import StatsAverage, { StatsType } from "@/components/StatsAverage";
import CardSkeleton from "@/components/CardSkeleton";
import StatsSkeleton from "@/components/StatsSkeleton";
import { getPredictions, getStats, getLastUpdate } from "@/services/api";

export default function HomeClient() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [predictions, setPredictions] = useState<any[]>([]);
  const [stats, setStats] = useState<StatsType | null>(null);
  const [lastUpdate, setLastUpdate] = useState("");
  const [selectedLeague, setSelectedLeague] = useState<string>("all");
  const [selectedDate, setSelectedDate] = useState<string>("today");

  const leagues = [
    { id: "all", name: "🌍 Todas as Ligas" },
    { id: 39, name: "🇬🇧 Premier League" },
    { id: 140, name: "🇪🇸 La Liga" },
    { id: 135, name: "🇮🇹 Serie A" },
    { id: 78, name: "🇩🇪 Bundesliga" },
    { id: 61, name: "🇫🇷 Ligue 1" },
    { id: 94, name: "🇵🇹 Primeira Liga" },
    { id: 88, name: "🇳🇱 Eredivisie" },
    { id: 2, name: "🏆 Champions League" },
  ];

  const getLeagueName = (id: number) => {
    const league = leagues.find((l) => String(l.id) === String(id));
    return league ? league.name : "🏳️ Liga Desconhecida";
  };

  // Calcular datas (hoje, amanhã, depois)
  const dates = {
    today: new Date(),
    tomorrow: new Date(Date.now() + 86400000),
    after: new Date(Date.now() + 2 * 86400000),
  };

  const formatDate = (d: Date) =>
    d.toISOString().split("T")[0]; // yyyy-mm-dd

  // Filtros guardados
  useEffect(() => {
    const savedLeague = localStorage.getItem("selectedLeague");
    const savedDate = localStorage.getItem("selectedDate");
    if (savedLeague) setSelectedLeague(savedLeague);
    if (savedDate) setSelectedDate(savedDate);
  }, []);

  useEffect(() => {
    if (selectedLeague) localStorage.setItem("selectedLeague", selectedLeague);
    if (selectedDate) localStorage.setItem("selectedDate", selectedDate);
  }, [selectedLeague, selectedDate]);

  // Fetch de dados
  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      setError("");
      try {
        const [preds, statsData, lastUpdateObj] = await Promise.all([
          getPredictions(),
          getStats(),
          getLastUpdate(),
        ]);
        setPredictions(preds || []);
        setStats(statsData || null);

        const lastUpdateRaw = lastUpdateObj?.last_update;
        if (lastUpdateRaw) {
          const dateObj = new Date(lastUpdateRaw.replace(" ", "T"));
          setLastUpdate(
            dateObj.toLocaleDateString("pt-PT", {
              day: "2-digit",
              month: "2-digit",
              year: "numeric",
            }) +
              " " +
              dateObj.toLocaleTimeString("pt-PT", {
                hour: "2-digit",
                minute: "2-digit",
              })
          );
        }

        if ((!preds || preds.length === 0) && (!statsData || Object.keys(statsData).length === 0)) {
          setError("Sem dados disponíveis no momento.");
        }
      } catch (err: any) {
        setError("Falha ao carregar dados. Tente novamente mais tarde.");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, []);

  // Filtrar por liga e data
  const filteredPredictions = predictions.filter((p) => {
    const matchDate = p.date ? p.date.split("T")[0] : "";
    const targetDate = formatDate(dates[selectedDate as keyof typeof dates]);
    const leagueMatch = selectedLeague === "all" || String(p.league_id) === String(selectedLeague);
    return leagueMatch && matchDate === targetDate;
  });

  // ====== LOADING / ERRO ======
  if (loading) {
    return (
      <div className="min-h-screen container mx-auto px-4 py-8 md:py-16">
        <Header />
        <main className="space-y-12 md:space-y-16">
          <InfoCard />
          <StatsSkeleton />
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[...Array(3)].map((_, idx) => (
              <CardSkeleton key={idx} />
            ))}
          </div>
        </main>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center text-center px-4">
        <Header />
        <div className="mt-12 text-red-400 font-semibold">{error}</div>
      </div>
    );
  }

  // ====== UI PRINCIPAL ======
  return (
    <div className="min-h-screen container mx-auto px-4 py-8 md:py-16">
      <Header />
      <main className="space-y-12 md:space-y-16">
        <InfoCard />
        {stats && <StatsAverage stats={stats} />}

        {/* FILTROS */}
        <div className="flex flex-col md:flex-row items-center justify-center gap-4 mb-8">
          {/* Filtro de Ligas */}
          <select
            value={selectedLeague}
            onChange={(e) => setSelectedLeague(e.target.value)}
            className="bg-gray-800 text-white px-5 py-2 rounded-xl border border-gray-700 focus:outline-none focus:ring-2 focus:ring-green-400 shadow-lg"
          >
            {leagues.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>

          {/* Filtro de Datas */}
          <div className="flex gap-2">
            {[
              { key: "today", label: "Hoje" },
              { key: "tomorrow", label: "Amanhã" },
              { key: "after", label: "Depois de Amanhã" },
            ].map((d) => (
              <button
                key={d.key}
                onClick={() => setSelectedDate(d.key)}
                className={`px-4 py-2 rounded-lg font-medium transition ${
                  selectedDate === d.key
                    ? "bg-green-500 text-white"
                    : "bg-gray-800 text-gray-300 hover:bg-gray-700"
                }`}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>

        {/* 🏆 Jogo em destaque */}
        {filteredPredictions.length > 0 ? (
          <>
            <div className="bg-gray-900 p-6 rounded-2xl shadow-lg border border-gray-800 hover:border-green-500 transition">
              {/* Liga + logótipo */}
              <div className="flex items-center justify-center mb-2 space-x-2">
                {filteredPredictions[0].league_logo && (
                  <img
                    src={filteredPredictions[0].league_logo}
                    alt="liga"
                    className="w-6 h-6 rounded-full border border-gray-700"
                  />
                )}
                <p className="text-sm text-gray-400 text-center">
                  {getLeagueName(filteredPredictions[0].league_id)}
                </p>
              </div>

              {/* Equipas */}
              <div className="flex items-center justify-center mb-3 space-x-2">
                {filteredPredictions[0].home_logo && (
                  <img
                    src={filteredPredictions[0].home_logo}
                    alt="home"
                    className="w-10 h-10 rounded-full border border-gray-700"
                  />
                )}
                <span className="text-white font-semibold">
                  {filteredPredictions[0].home_team} vs{" "}
                  {filteredPredictions[0].away_team}
                </span>
                {filteredPredictions[0].away_logo && (
                  <img
                    src={filteredPredictions[0].away_logo}
                    alt="away"
                    className="w-10 h-10 rounded-full border border-gray-700"
                  />
                )}
              </div>

              <p className="text-center text-sm text-gray-400 mb-2">
                {new Date(filteredPredictions[0].date).toLocaleString("pt-PT")}
              </p>
              <div className="text-center text-2xl font-bold text-green-400 mb-2">
                {filteredPredictions[0].predicted_score?.home} -{" "}
                {filteredPredictions[0].predicted_score?.away}
              </div>
              <p className="text-center text-gray-300">
                Confiança:{" "}
                {(filteredPredictions[0].confidence * 100).toFixed(1)}%
              </p>
            </div>

            {/* ⚽ Outros jogos */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {filteredPredictions.slice(1).map((match, idx) => (
                <div
                  key={idx}
                  className="bg-gray-900 p-4 rounded-xl border border-gray-800 hover:border-green-500 transition"
                >
                  <div className="flex items-center justify-center mb-1 space-x-2">
                    {match.league_logo && (
                      <img
                        src={match.league_logo}
                        alt="liga"
                        className="w-5 h-5 rounded-full border border-gray-700"
                      />
                    )}
                    <p className="text-sm text-gray-400 text-center">
                      {getLeagueName(match.league_id)}
                    </p>
                  </div>
                  <div className="flex items-center justify-center mb-2">
                    {match.home_logo && (
                      <img
                        src={match.home_logo}
                        alt="home"
                        className="w-8 h-8 mr-2 rounded-full border border-gray-700"
                      />
                    )}
                    <span className="text-white font-semibold">
                      {match.home_team} vs {match.away_team}
                    </span>
                    {match.away_logo && (
                      <img
                        src={match.away_logo}
                        alt="away"
                        className="w-8 h-8 ml-2 rounded-full border border-gray-700"
                      />
                    )}
                  </div>
                  <div className="text-center text-green-400 font-bold">
                    {match.predicted_score?.home} -{" "}
                    {match.predicted_score?.away}
                  </div>
                  <p className="text-center text-sm text-gray-400 mt-1">
                    Confiança: {(match.confidence * 100).toFixed(1)}%
                  </p>
                </div>
              ))}
            </div>
          </>
        ) : (
          <p className="text-center text-gray-400 mt-10">
            Nenhum jogo encontrado para esta data.
          </p>
        )}

        {lastUpdate && (
          <div className="w-full text-center mt-10">
            <span className="text-xs text-gray-400">
              Última atualização: {lastUpdate}
            </span>
          </div>
        )}
      </main>
    </div>
  );
}
