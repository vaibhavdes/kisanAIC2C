import React, { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { BUILTIN_LANGUAGES, hasDictionary, makeT } from "./constants/i18n";
import { invalidate } from "./hooks";
import { Json, Locale, NodeLanguage, View } from "./types";
import { Header } from "./components/Header";
import { LanguageModal } from "./components/LanguageModal";
import { PipelineStepper } from "./components/PipelineStepper";
import { MobileNav } from "./components/MobileNav";
import { ErrorNote, Loading } from "./components/ui";
import { HomeView } from "./views/HomeView";
import { WeatherView } from "./views/WeatherView";
import { SoilView } from "./views/SoilView";
import { CropRecView } from "./views/CropRecView";
import { AdvisoryView } from "./views/AdvisoryView";
import { DiagnoseView } from "./views/DiagnoseView";

const FarmFormView = lazy(() => import("./views/FarmFormView").then((m) => ({ default: m.FarmFormView })));
const ExpertView = lazy(() => import("./views/ExpertView").then((m) => ({ default: m.ExpertView })));

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

export function App() {
  const [view, setViewState] = useState<View>("home");
  const [locale, setLocale] = useState<Locale>(() => readStorage("kisanai_locale") || "en-IN");
  const [languages, setLanguages] = useState<NodeLanguage[]>(BUILTIN_LANGUAGES.map((l) => ({ ...l, machine_translated: false })));
  const [remote, setRemote] = useState<Record<string, Record<string, string>>>({});
  const [showLangModal, setShowLangModal] = useState(() => !readStorage("kisanai_locale"));
  const [farms, setFarms] = useState<Json[]>([]);
  const [farmsLoaded, setFarmsLoaded] = useState(false);
  const [selected, setSelected] = useState<string>(() => readStorage("kisanai_selected_farm") || "");
  const [editing, setEditing] = useState<Json | null>(null);
  const [error, setError] = useState("");

  const t = useMemo(() => makeT(locale, remote[locale]), [locale, remote]);
  // The expert workspace is English-only for officers, whatever language the farmer app is in.
  const expertT = useMemo(() => makeT("en-IN"), []);
  const farm = farms.find((f) => f.id === selected) || farms[0];

  useEffect(() => {
    document.documentElement.lang = locale.split("-")[0];
  }, [locale]);

  // The node says which farmer languages it serves (a Brazil node offers Portuguese, an India node Indian languages).
  useEffect(() => {
    api<Json>("/api/v1/node").then((node) => {
      if (!node.languages?.length) return;
      setLanguages(node.languages);
      const saved = readStorage("kisanai_locale");
      if (!saved || !node.languages.some((l: NodeLanguage) => l.locale === saved)) setLocale(node.default_locale || node.languages[0].locale);
    }).catch(() => undefined);
  }, []);

  // Languages without a hand-written dictionary come machine-translated from the API (Google Cloud Translation).
  useEffect(() => {
    if (hasDictionary(locale) || remote[locale]) return;
    api<Json>(`/api/v1/i18n/${locale}`)
      .then((bundle) => setRemote((prev) => ({ ...prev, [locale]: bundle.strings })))
      .catch(() => undefined);
  }, [locale, remote]);

  const setView = useCallback((next: View) => {
    setViewState(next);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  const loadFarms = useCallback(async (preferId?: string) => {
    try {
      const list = await api<Json[]>("/api/v1/farms");
      setFarms(list);
      const pick = list.find((f) => f.id === (preferId || selected)) || list[0];
      setSelected(pick ? pick.id : "");
      writeStorage("kisanai_selected_farm", pick ? pick.id : null);
      setError("");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setFarmsLoaded(true);
    }
  }, [selected]);

  useEffect(() => {
    loadFarms();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectFarm = (id: string) => {
    setSelected(id);
    writeStorage("kisanai_selected_farm", id);
  };

  const chooseLanguage = (next: Locale) => {
    setLocale(next);
    writeStorage("kisanai_locale", next);
    setShowLangModal(false);
  };

  const deleteFarm = async (id: string) => {
    await api(`/api/v1/farms/${id}`, { method: "DELETE" });
    invalidate(`/api/v1/farms/${id}`);
    await loadFarms();
    setView("home");
  };

  const farmSaved = async (saved: Json) => {
    invalidate(`/api/v1/farms/${saved.id}`);
    setEditing(null);
    await loadFarms(saved.id);
    setView("weather");
  };

  const common = { t, locale, farm, go: setView };

  return (
    <div className="shell">
      <Header t={t} languageName={languages.find((l) => l.locale === locale)?.name || locale} view={view} setView={setView} openLanguage={() => setShowLangModal(true)}
              farms={farms} selected={farm?.id || ""} onSelect={selectFarm} />
      {showLangModal && <LanguageModal t={t} locale={locale} languages={languages} choose={chooseLanguage} />}
      {view !== "home" && view !== "expert" && view !== "diagnose" && <PipelineStepper t={t} view={view} farm={farm} setView={setView} />}
      <main>
        <Suspense fallback={<Loading label={t("loading")} />}>
        {error && <ErrorNote t={t} message={error} onRetry={() => loadFarms()} />}
        {view === "home" && (
          <HomeView {...common} farms={farms} loaded={farmsLoaded}
                    onEdit={(f) => { setEditing(f); setView("farm"); }} onDelete={deleteFarm} />
        )}
        {view === "farm" && <FarmFormView t={t} locale={locale} editing={editing} onSaved={farmSaved} onCancel={() => { setEditing(null); setView("home"); }} />}
        {view === "weather" && <WeatherView {...common} />}
        {view === "soil" && <SoilView {...common} />}
        {view === "crops" && <CropRecView {...common} />}
        {view === "advice" && <AdvisoryView {...common} />}
        {view === "diagnose" && <DiagnoseView {...common} />}
        {view === "expert" && <ExpertView t={expertT} locale="en-IN" />}
        </Suspense>
      </main>
      <MobileNav t={t} view={view} farm={farm} setView={setView} />
    </div>
  );
}
