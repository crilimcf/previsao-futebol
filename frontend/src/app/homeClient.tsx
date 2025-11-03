"use client";
import { useEffect, useState, useRef } from "react";
import Header from "@/components/header";
import InfoCard from "@/components/infoCards";
import StatsAverage, { StatsType } from "@/components/StatsAverage";
import CardSkeleton from "@/components/CardSkeleton";
import StatsSkeleton from "@/components/StatsSkeleton";
import { getPredictions, getStats, getLastUpdate } from "@/services/api";
import { getFixturesByLeague } from "@/services/proxy";

// 🕒 Helper de tempo decorrido
function timeSince(date: number) {
  const seconds = Math.floor((Date.now() - date) / 1000);
  if (seconds < 60) return `${seconds}s atrás`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m atrás`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h atrás`;
}

export default function HomeClient() {
  // -------------------------------
  // Estados principais
  // -------------------------------
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");
  const [predictions, setPredictions] = useState<any[]>([]);
  const [stats, setStats] = useState<StatsType | null>(null);
  const [lastUpdate, setLastUpdate] = useState("");
  const [selectedLeague, setSelectedLeague] = useState<string>("all");
  const [selectedDate, setSelectedDate] = useState<string>("today");

  // Jogos Reais
  const [liveFixtures, setLiveFixtures] = useState<any[]>([]);
  const [loadingFixtures, setLoadingFixtures] = useState(false);
  const [lastFixturesUpdate, setLastFixturesUpdate] = useState<number | null>(null);

  const isManualRefresh = useRef(false);

  // -------------------------------
  // Ligas disponíveis
  // -------------------------------
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

  const dates = {
    today: new Date(),
    tomorrow: new Date(Date.now() + 86400000),
    after: new Date(Date.now() + 2 * 86400000),
  };
  const formatDate = (d: Date) => d.toISOString().split("T")[0];

  // -------------------------------
  // Guarda filtros
  // -------------------------------
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

  // -------------------------------
  // Fetch dados principais (predictions + stats)
  // -------------------------------
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

  // -------------------------------
  // Fetch jogos reais (via proxy)
  // -------------------------------
  async function loadFixtures(ignoreCache = false) {
    try {
      if (selectedLeague === "all") return;
      setLoadingFixtures(true);
      console.log(`🔄 Carregando jogos da liga ${selectedLeague}...`);
      const data = await getFixturesByLeague(Number(selectedLeague), ignoreCache ? 0 : 5);
      setLiveFixtures(data.response || []);
      setLastFixturesUpdate(Date.now());
      console.log(`✅ ${data.response?.length || 0} jogos carregados.`);
    } catch (err) {
      console.error("Erro ao carregar fixtures:", err);
    } finally {
      setLoadingFixtures(false);
      isManualRefresh.current = false;
    }
  }

  useEffect(() => {
    loadFixtures();
  }, [selectedLeague]);

  // -------------------------------
  // Filtro de previsões
  // -------------------------------
  const filteredPredictions = predictions.filter((p) => {
    const matchDate = p.date ? p.date.split("T")[0] : "";
    const targetDate = formatDate(dates[selectedDate as keyof typeof dates]);
    const leagueMatch = selectedLeague === "all" || String(p.league_id) === String(selectedLeague);
    return leagueMatch && matchDate === targetDate;
  });

  // -------------------------------
  // UI: LOADING / ERRO
  // -------------------------------
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

  // -------------------------------
  // UI: PRINCIPAL
  // -------------------------------
  return (
    <div className="min-h-screen container mx-auto px-4 py-8 md:py-16">
      <Header />
      <main className="space-y-12 md:space-y-16">
        <InfoCard />
        {stats && <StatsAverage stats={stats} />}

        {/* FILTROS */}
        <div className="flex flex-col md:flex-row items-center justify-center gap-4 mb-8">
          {/* Ligas */}
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

          {/* Datas */}
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

        {/* ⚽ BLOCO: JOGOS REAIS */}
        <div className="bg-gray-900 p-6 rounded-2xl shadow-lg border border-gray-800 mb-10">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-green-400">
              Jogos Reais (via API-Football)
            </h2>

            {/* Botão atualizar */}
            <button
              onClick={() => {
                isManualRefresh.current = true;
                loadFixtures(true);
              }}
              disabled={loadingFixtures}
              className="flex items-center gap-2 bg-gray-800 text-sm text-gray-200 px-4 py-2 rounded-lg hover:bg-gray-700 transition"
            >
              🔁 {loadingFixtures ? "A atualizar..." : "Atualizar"}
            </button>
          </div>

          {/* Estado de carregamento */}
          {loadingFixtures && (
            <div className="text-center text-sm text-gray-400 animate-pulse mb-4">
              ⏳ A carregar jogos reais...
            </div>
          )}

          {/* Lista de jogos */}
          {liveFixtures.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {liveFixtures.map((f: any) => (
                <div
                  key={f.fixture.id}
                  className="p-4 rounded-xl border border-gray-800 bg-gray-950 hover:border-green-500 transition"
                >
                  <div className="flex items-center justify-center space-x-2 mb-2">
                    <img src={f.teams.home.logo} className="w-6 h-6" />
                    <span className="text-white font-medium">{f.teams.home.name}</span>
                    <span className="text-gray-400">vs</span>
                    <span className="text-white font-medium">{f.teams.away.name}</span>
                    <img src={f.teams.away.logo} className="w-6 h-6" />
                  </div>
                  <p className="text-sm text-center text-gray-400">
                    {new Date(f.fixture.date).toLocaleString("pt-PT")}
                  </p>
                  <p className="text-xs text-center text-gray-500 mt-1">
                    {f.league.name} ({f.league.country})
                  </p>
                </div>
              ))}
            </div>
          ) : (
            !loadingFixtures && (
              <p className="text-center text-gray-400 mt-4">
                Nenhum jogo encontrado para esta liga.
              </p>
            )
          )}

          {/* Badge última atualização */}
          {lastFixturesUpdate && (
            <div className="text-xs text-center text-gray-500 mt-4">
              Última atualização: {timeSince(lastFixturesUpdate)}
            </div>
          )}
        </div>

        {/* Bloco de previsões (original) */}
        {filteredPredictions.length > 0 ? (
          <>
            {/* Aqui entra o teu bloco original de previsões */}
          </>
        ) : (
          <p className="text-center text-gray-400 mt-10">
            Nenhum jogo encontrado para esta data.
          </p>
        )}

        {lastUpdate && (
          <div className="w-full text-center mt-10">
            <span className="text-xs text-gray-400">
              Última atualização global: {lastUpdate}
            </span>
          </div>
        )}
      </main>
    </div>
  );
}
