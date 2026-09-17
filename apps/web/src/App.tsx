import React, { useEffect, useState } from "react";
import {
  Activity, AlertTriangle, ArrowRight, BookOpen, CloudRain,
  Languages, Leaf, MapPin, Microscope, RefreshCw, Sprout
} from "lucide-react";
import { api } from "./api";
import { View, Locale, Json } from "./types";
import { copy } from "./constants/localization";

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
  const [view, setView] = useState<View>("home");
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
  const [farms, setFarms] = useState<Json[]>(() => {
    try {
      const saved = localStorage.getItem("kisanai_cached_farm");
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.id === "farm_default_mh" || parsed.name === "Vidarbha Demonstration Farm" || String(parsed.name).toLowerCase().includes("demonstration")) {
          localStorage.removeItem("kisanai_cached_farm");
          return [];
        }
        return [parsed];
      }
      return [];
    } catch {
      return [];
    }
  });
  const [selected, setSelected] = useState<string>(() => {
    try {
      const saved = localStorage.getItem("kisanai_cached_farm");
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.id === "farm_default_mh" || parsed.name === "Vidarbha Demonstration Farm" || String(parsed.name).toLowerCase().includes("demonstration")) {
          return "";
        }
        return parsed.id || "";
      }
      return "";
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
  const [season, setSeason] = useState("kharif");
  const [loadingWeather, setLoadingWeather] = useState(false);
  const [loadingRecs, setLoadingRecs] = useState(false);

  const t = copy[locale] || copy["en-IN"];
  const farm = farms.find(f => f.id === selected) || farms[0];

  const selectLanguage = (l: Locale) => {
    setLocale(l);
    localStorage.setItem("kisanai_locale", l);
    localStorage.setItem("kisanai_locale_selected", "true");
    setShowLangModal(false);
  };

  const load = async () => {
    try {
      let list = await api<Json[]>("/api/v1/farms");
      // Filter out any legacy demonstration farms
      list = (list || []).filter(
        f => f.id !== "farm_default_mh" && !String(f.name || "").toLowerCase().includes("demonstration")
      );

      if (list.length === 0) {
        const cachedStr = localStorage.getItem("kisanai_cached_farm");
        if (cachedStr) {
          try {
            const cachedFarm = JSON.parse(cachedStr);
            if (
              cachedFarm.id === "farm_default_mh" ||
              cachedFarm.name === "Vidarbha Demonstration Farm" ||
              String(cachedFarm.name || "").toLowerCase().includes("demonstration")
            ) {
              localStorage.removeItem("kisanai_cached_farm");
            } else {
              const synced = await api<Json>("/api/v1/farms", {
                method: "POST",
                body: JSON.stringify(cachedFarm)
              });
              list = [synced];
            }
          } catch (e) {
            console.warn("Could not sync cached farm to server", e);
          }
        }
      }
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
      await loadSatMap(satIndex);
      await loadOperational();
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
    try {
      const res = await api<Json>(`/api/v1/farms/${farm.id}/satellite/map?index=${index}&days=90`);
      setSatMap(res);
    } catch (err) {
      console.warn("Satellite map error", err);
    }
  };

  const loadOperational = async () => {
    if (!farm) return;
    try {
      const data = await api<Json>(`/api/v1/farms/${farm.id}/weather/operational`);
      setOperational(data);
    } catch (e) {
      console.warn("Operational forecast fetch issue", e);
    }
  };

  const loadCropRecs = async (targetSeason?: string) => {
    if (!farm) return;
    setLoadingRecs(true);
    try {
      const s = targetSeason || season;
      const data = await api<Json>(`/api/v1/farms/${farm.id}/crop-recommendations?season=${s}&locale=${locale}`);
      setCropRecs(data);
    } catch (err) {
      console.warn("Crop recommendation fetch error", err);
    } finally {
      setLoadingRecs(false);
    }
  };

  const handleSeasonChange = (newSeason: string) => {
    setSeason(newSeason);
    loadCropRecs(newSeason);
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!farm) return;
    const fetchExistingOrRefresh = async () => {
      try {
        setLoadingWeather(true);
        const existing = await api<Json[]>(`/api/v1/farms/${farm.id}/evidence`);
        const hasForecast = existing?.some(
          (s: any) =>
            (s.kind === "weather_forecast" || s.kind === "weather_nowcast") &&
            Array.isArray(s.values) &&
            s.values.some((v: any) => typeof v.name === "string" && v.name.startsWith("rainfall_"))
        );
        if (existing && existing.length > 0 && hasForecast) {
          setEvidence(existing);
        } else {
          const fresh = await api<Json[]>(`/api/v1/farms/${farm.id}/evidence/refresh`, { method: "POST" });
          setEvidence(fresh);
        }
      } catch (e) {
        console.warn("Evidence fetch issue", e);
      } finally {
        setLoadingWeather(false);
      }
    };
    fetchExistingOrRefresh();
    loadSatMap("NDVI");
    loadOperational();
    loadCropRecs(season);
  }, [farm?.id, locale]);

  const deleteFarm = async (farmId: string) => {
    try {
      await api(`/api/v1/farms/${farmId}`, { method: "DELETE" });
      try {
        const myIds = JSON.parse(localStorage.getItem("kisanai_my_farm_ids") || "[]");
        localStorage.setItem(
          "kisanai_my_farm_ids",
          JSON.stringify(myIds.filter((id: string) => id !== farmId))
        );
      } catch {}
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
            farms={farms}
            selected={selected}
            setSelected={setSelected}
            go={setView}
            onDeleteFarm={deleteFarm}
          />
        )}
        {view === "farm" && (
          <FarmFormView
            t={t}
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
            go={setView}
          />
        )}
        {view === "crops" && (
          <CropRecView
            t={t}
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

      <MobileNav view={view} farm={farm} setView={setView} />
    </div>
  );
}
