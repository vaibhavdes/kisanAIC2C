import { useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { api } from "./api";
import { View, Locale, Json } from "./types";
import { copy } from "./constants/localization";
import { currentSeason } from "./utils/season";

// Components
import { Header } from "./components/Header";
import { LanguageModal } from "./components/LanguageModal";
import { PipelineStepper } from "./components/PipelineStepper";
import { MobileNav } from "./components/MobileNav";

// Views
import { HomeView } from "./views/HomeView";
import { FarmFormView } from "./views/FarmFormView";
import { WeatherView } from "./views/WeatherView";
import { SoilView } from "./views/SoilView";
import { CropRecView } from "./views/CropRecView";
import { AdvisoryView } from "./views/AdvisoryView";
import { DiagnoseView } from "./views/DiagnoseView";
import { ExpertView } from "./views/ExpertView";

export function App() {
  const [view, setViewState] = useState<View>("home");
  // The farm screen edits the open farm unless the farmer asked for a new one.
  const [addingFarm, setAddingFarm] = useState(false);
  const setView = (next: View) => {
    setAddingFarm(false);
    setViewState(next);
  };
  const startNewFarm = () => {
    setAddingFarm(true);
    setViewState("farm");
  };
  const [locale, setLocale] = useState<Locale>(() => {
    const saved = localStorage.getItem("kisanai_locale");
    if (saved && ["en-IN", "hi-IN", "mr-IN", "te-IN", "kn-IN"].includes(saved)) {
      return saved as Locale;
    }
    return "en-IN";
  });
  const [showLangModal, setShowLangModal] = useState<boolean>(
    () => !localStorage.getItem("kisanai_locale_selected")
  );
  const [farms, setFarms] = useState<Json[]>([]);
  const [selected, setSelected] = useState<string>(() => {
    try {
      return JSON.parse(localStorage.getItem("kisanai_cached_farm") || "{}").id || "";
    } catch {
      return "";
    }
  });
  const [error, setError] = useState("");

  // Global Evidence & Pipeline Cache
  const [evidence, setEvidence] = useState<Json[]>([]);
  const [satMap, setSatMap] = useState<Json | null>(null);
  const [satIndex, setSatIndex] = useState("NDVI");
  const [operational, setOperational] = useState<Json | null>(null);
  const [cropRecs, setCropRecs] = useState<Json | null>(null);
  const [season, setSeason] = useState<string>(() => currentSeason());
  const [loadingWeather, setLoadingWeather] = useState(false);
  const [loadingRecs, setLoadingRecs] = useState(false);

  const t = copy[locale] || copy["en-IN"];
  const farm = farms.find(f => f.id === selected) || farms[0];
  // Replies for a farm that is no longer open are dropped, so a slow reply cannot show another farm's data.
  const openFarmId = useRef<string | undefined>(undefined);
  openFarmId.current = farm?.id;
  const stillOpen = (id: string) => openFarmId.current === id;

  const selectLanguage = (l: Locale) => {
    setLocale(l);
    localStorage.setItem("kisanai_locale", l);
    localStorage.setItem("kisanai_locale_selected", "true");
    setShowLangModal(false);
  };

  const load = async () => {
    try {
      // Farms live in the server's database; the browser only remembers which one was open.
      const list = (await api<Json[]>("/api/v1/farms")) || [];
      setFarms(list);
      if (list.length > 0) {
        const match = list.find(f => f.id === selected) || list[0];
        setSelected(match.id);
        localStorage.setItem("kisanai_cached_farm", JSON.stringify(match));
      } else {
        setSelected("");
        localStorage.removeItem("kisanai_cached_farm");
      }
    } catch (e) {
      setError(String((e as Error).message));
    }
  };

  const refreshEvidence = async () => {
    if (!farm) return;
    setLoadingWeather(true);
    try {
      const snaps = await api<Json[]>(`/api/v1/farms/${farm.id}/evidence/refresh`, { method: "POST" });
      setEvidence(snaps);
      await loadOperational(season);
      await loadSatMap(satIndex);
      await loadCropRecs(season);
    } catch (err) {
      alert((err as Error).message);
    } finally {
      setLoadingWeather(false);
    }
  };

  const loadSatMap = async (index: string) => {
    if (!farm) return;
    setSatIndex(index);
    const id = farm.id;
    try {
      const res = await api<Json>(`/api/v1/farms/${id}/satellite/map?index=${index}&days=30&locale=${locale}`);
      if (stillOpen(id)) setSatMap(res);
    } catch (err) {
      console.warn("Satellite map error", err);
    }
  };

  const loadOperational = async (targetSeason?: string) => {
    if (!farm) return;
    const id = farm.id;
    try {
      const s = targetSeason || season;
      const data = await api<Json>(`/api/v1/farms/${id}/weather/operational?season=${s}&locale=${locale}`);
      if (stillOpen(id)) setOperational(data);
    } catch (e) {
      console.warn("Operational forecast fetch issue", e);
    }
  };

  const loadCropRecs = async (targetSeason?: string) => {
    if (!farm) return;
    setLoadingRecs(true);
    const id = farm.id;
    try {
      const s = targetSeason || season;
      const data = await api<Json>(`/api/v1/farms/${id}/crop-recommendations?season=${s}&locale=${locale}`);
      if (stillOpen(id)) setCropRecs(data);
    } catch (err) {
      console.warn("Crop recommendation fetch error", err);
    } finally {
      setLoadingRecs(false);
    }
  };

  const handleSeasonChange = (newSeason: string) => {
    setSeason(newSeason);
    loadCropRecs(newSeason);
    loadOperational(newSeason);
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    setEvidence([]);
    setOperational(null);
    setCropRecs(null);
    setSatMap(null);
    if (farm) localStorage.setItem("kisanai_cached_farm", JSON.stringify(farm));
  }, [farm?.id]);

  useEffect(() => {
    if (!farm) return;
    const loadWeather = async () => {
      setLoadingWeather(true);
      try {
        // The operational endpoint refetches the forecast on the server when it is older than 3 hours,
        // so load it first and then read the evidence it produced.
        await loadOperational(season);
        const snapshots = await api<Json[]>(`/api/v1/farms/${farm.id}/evidence`);
        if (stillOpen(farm.id)) setEvidence(snapshots);
      } catch (e) {
        console.warn("Weather load issue", e);
      } finally {
        setLoadingWeather(false);
      }
    };
    loadWeather();
    loadCropRecs(season);
  }, [farm?.id, locale]);

  // The satellite map is cached on the server; a language change only refetches its plain-language text.
  useEffect(() => {
    if (farm) loadSatMap(satIndex);
  }, [farm?.id, locale]);

  const deleteFarm = async (farmId: string) => {
    try {
      await api(`/api/v1/farms/${farmId}`, { method: "DELETE" });
      const remaining = farms.filter((f) => f.id !== farmId);
      setFarms(remaining);
      if (selected === farmId) {
        if (remaining.length > 0) {
          setSelected(remaining[0].id);
          localStorage.setItem("kisanai_cached_farm", JSON.stringify(remaining[0]));
        } else {
          setSelected("");
          localStorage.removeItem("kisanai_cached_farm");
          setView("farm");
        }
      }
    } catch (e) {
      alert((e as Error).message || "Failed to delete farm");
    }
  };

  return (
    <div className="shell">
      <Header
        t={t}
        locale={locale}
        view={view}
        setView={setView}
        setShowLangModal={setShowLangModal}
        farms={farms}
        selected={selected}
        setSelected={setSelected}
      />

      {showLangModal && (
        <LanguageModal
          t={t}
          locale={locale}
          selectLanguage={selectLanguage}
        />
      )}

      {view !== "home" && view !== "expert" && (
        <PipelineStepper
          t={t}
          view={view}
          farm={farm}
          setView={setView}
        />
      )}

      <main>
        {error && (
          <div className="notice error">
            <AlertTriangle size={18} />
            <span>{error}</span>
            <button
              onClick={() => setError("")}
              style={{ background: "transparent", border: 0, color: "white", cursor: "pointer", marginLeft: "8px" }}
            >
              ✕
            </button>
          </div>
        )}

        {view === "home" && (
          <HomeView
            t={t}
            locale={locale}
            farms={farms}
            selected={selected}
            setSelected={setSelected}
            go={setView}
            onDeleteFarm={deleteFarm}
            onNewFarm={startNewFarm}
            evidence={evidence}
            operational={operational}
            cropRecs={cropRecs}
            loadingWeather={loadingWeather}
            loadingRecs={loadingRecs}
          />
        )}
        {view === "farm" && (
          <FarmFormView
            key={addingFarm || !farm ? "new" : `${farm.id}-${farm.version}`}
            t={t}
            farm={addingFarm ? undefined : farm}
            done={async (id) => {
              await load();
              setSelected(id);
              setView("weather");
            }}
          />
        )}
        {view === "weather" && (
          <WeatherView
            t={t}
            locale={locale}
            farm={farm}
            evidence={evidence}
            operational={operational}
            satMap={satMap}
            loadingWeather={loadingWeather}
            refreshEvidence={refreshEvidence}
            go={setView}
          />
        )}
        {view === "soil" && (
          <SoilView
            t={t}
            locale={locale}
            farm={farm}
            cropRecs={cropRecs}
            season={season}
            go={setView}
            onSoilSaved={() => loadCropRecs(season)}
          />
        )}
        {view === "crops" && (
          <CropRecView
            t={t}
            locale={locale}
            farm={farm}
            cropRecs={cropRecs}
            loadingRecs={loadingRecs}
            season={season}
            handleSeasonChange={handleSeasonChange}
            loadCropRecs={loadCropRecs}
            go={setView}
          />
        )}
        {view === "advice" && (
          <AdvisoryView
            t={t}
            locale={locale}
            farm={farm}
            satMap={satMap}
            satIndex={satIndex}
            loadSatMap={loadSatMap}
            evidence={evidence}
            season={season}
            handleSeasonChange={handleSeasonChange}
            go={setView}
          />
        )}
        {view === "diagnose" && (
          <DiagnoseView t={t} locale={locale} farm={farm} go={setView} />
        )}
        {view === "expert" && (
          <ExpertView t={t} />
        )}
      </main>

      <MobileNav t={t} view={view} farm={farm} setView={setView} />
    </div>
  );
}
