import React, { FormEvent, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Crosshair, MapPin, Search, Undo2, X } from "lucide-react";
import { api } from "../api";
import { useResource } from "../hooks";
import { Json, Locale, T } from "../types";
import { ErrorNote, StageHeader } from "../components/ui";
import { FieldMap, LatLon, polygonAreaHa } from "../components/FieldMap";

interface FarmFormViewProps {
  t: T;
  locale: Locale;
  editing: Json | null;
  onSaved: (farm: Json) => void;
  onCancel: () => void;
}

interface Place {
  latitude: number;
  longitude: number;
  country_code: string;
  state_code: string;
  state_name: string;
  district: string;
  village?: string;
  pincode?: string | null;
  label?: string;
}

const WATER = ["rainfed", "supplemental_irrigation", "irrigated"] as const;
const SOILS = ["black", "red", "alluvial", "loam", "clay", "sandy", "unknown"] as const;
const DEFAULT_CENTER: LatLon = [20.59, 78.96];

export function FarmFormView({ t, locale, editing, onSaved, onCancel }: FarmFormViewProps) {
  const [place, setPlace] = useState<Place | null>(() => editing ? {
    latitude: editing.location.latitude, longitude: editing.location.longitude, country_code: editing.country_code,
    state_code: editing.state_code, state_name: editing.state_name, district: editing.district, village: editing.village, pincode: editing.pincode,
  } : null);
  const [center, setCenter] = useState<LatLon>(editing ? [editing.location.latitude, editing.location.longitude] : DEFAULT_CENTER);
  const [corners, setCorners] = useState<LatLon[]>(editing?.boundary_coordinates || []);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Place[]>([]);
  const [offices, setOffices] = useState<Json[]>([]);
  const [finding, setFinding] = useState(false);
  const [findError, setFindError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const [form, setForm] = useState(() => ({
    name: editing?.name || "",
    area_value: editing ? String(editing.area_value) : "",
    area_unit: editing?.area_unit || (locale.endsWith("-IN") ? "acre" : "hectare"),
    water_access: editing?.water_access || "rainfed",
    soil_type: editing?.soil_type || "unknown",
    crop_status: editing?.crop_status || "planning",
    current_crop: editing?.current_crop || "",
    sowing_date: editing?.sowing_date || "",
    previous_crop: editing?.previous_crop || "",
  }));

  const catalog = useResource<Json>(place ? `/api/v1/catalog/crops?locale=${locale}&country_code=${place.country_code}&state_code=${place.state_code}` : `/api/v1/catalog/crops?locale=${locale}`);
  const crops: Json[] = catalog.data?.crops || [];

  const plottedHa = useMemo(() => polygonAreaHa(corners), [corners]);
  useEffect(() => {
    if (corners.length >= 3) {
      const value = form.area_unit === "acre" ? plottedHa * 2.47105 : plottedHa;
      setForm((prev) => ({ ...prev, area_value: value.toFixed(2) }));
    }
  }, [plottedHa]);

  const applyPlace = (p: Place, zoomTo = true) => {
    setPlace(p);
    if (zoomTo) setCenter([p.latitude, p.longitude]);
    setResults([]);
    setFindError("");
  };

  const search = async (e?: FormEvent) => {
    e?.preventDefault();
    const text = query.trim();
    if (!text) return;
    setFinding(true);
    setFindError("");
    setOffices([]);
    try {
      if (/^\d{6}$/.test(text)) {
        const pin = await api<Json>(`/api/v1/geo/pincode/${text}`);
        setOffices(pin.post_offices.filter((o: Json) => o.latitude && o.longitude));
        applyPlace({ latitude: pin.latitude, longitude: pin.longitude, country_code: "IN", state_code: pin.state_code, state_name: pin.state_name,
                     district: pin.district, village: pin.village, pincode: text });
      } else {
        const found = await api<Place[]>(`/api/v1/geo/search?q=${encodeURIComponent(text)}`);
        if (!found.length) setFindError(t("place_not_found"));
        setResults(found);
      }
    } catch (err) {
      setFindError((err as Error).message);
    } finally {
      setFinding(false);
    }
  };

  const reverse = async (lat: number, lon: number) => {
    try {
      const p = await api<Place>(`/api/v1/geo/reverse?latitude=${lat}&longitude=${lon}`);
      applyPlace(p, false);
    } catch (err) {
      setFindError((err as Error).message);
    }
  };

  const useGps = () => {
    if (!navigator.geolocation) {
      setFindError(t("gps_unavailable"));
      return;
    }
    setFinding(true);
    setFindError("");
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const point: LatLon = [Number(pos.coords.latitude.toFixed(6)), Number(pos.coords.longitude.toFixed(6))];
        setCenter(point);
        await reverse(point[0], point[1]);
        setFinding(false);
      },
      (err) => {
        setFinding(false);
        setFindError(err.code === 1 ? t("gps_denied") : t("gps_unavailable"));
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 },
    );
  };

  // Name the location once the field is drawn somewhere we have not named yet.
  useEffect(() => {
    if (corners.length < 3) return;
    const lat = corners.reduce((s, c) => s + c[0], 0) / corners.length;
    const lon = corners.reduce((s, c) => s + c[1], 0) / corners.length;
    if (!place || Math.abs(place.latitude - lat) > 0.05 || Math.abs(place.longitude - lon) > 0.05) reverse(lat, lon);
  }, [corners.length]);

  const point: LatLon = corners.length >= 3
    ? [Number((corners.reduce((s, c) => s + c[0], 0) / corners.length).toFixed(6)), Number((corners.reduce((s, c) => s + c[1], 0) / corners.length).toFixed(6))]
    : place ? [place.latitude, place.longitude] : center;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!place || !place.state_code || !place.district) {
      setSaveError(t("location_incomplete"));
      return;
    }
    const area = Number(form.area_value);
    if (!(area > 0)) {
      setSaveError(t("area_required"));
      return;
    }
    setSaving(true);
    setSaveError("");
    const body = {
      name: form.name.trim() || t("my_farm"),
      country_code: place.country_code || "IN",
      state_code: place.state_code,
      state_name: place.state_name || place.state_code,
      district: place.district,
      village: place.village || null,
      pincode: place.pincode || null,
      boundary_coordinates: corners.length >= 3 ? corners : [],
      area_value: area,
      area_unit: form.area_unit,
      location: { latitude: point[0], longitude: point[1], source: corners.length >= 3 ? "farmer" : "device", confirmed: true },
      water_access: form.water_access,
      soil_type: form.soil_type,
      crop_status: form.crop_status,
      current_crop: form.crop_status === "planted" ? form.current_crop || null : null,
      sowing_date: form.crop_status === "planted" && form.sowing_date ? form.sowing_date : null,
      previous_crop: form.previous_crop || null,
    };
    try {
      const saved = editing
        ? await api<Json>(`/api/v1/farms/${editing.id}?version=${editing.version}`, { method: "PUT", body: JSON.stringify(body) })
        : await api<Json>("/api/v1/farms", { method: "POST", body: JSON.stringify(body) });
      onSaved(saved);
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const cropOptions = (
    <>
      {crops.some((c) => c.regional) && <optgroup label={t("crops_common_here")}>
        {crops.filter((c) => c.regional).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </optgroup>}
      <optgroup label={t("crops_all")}>
        {crops.filter((c) => !c.regional).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
      </optgroup>
    </>
  );

  return (
    <section className="panel narrow">
      <StageHeader icon={<MapPin />} step={t("step_n", { n: 1 })} title={editing ? t("edit_farm") : t("add_farm")} subtitle={t("farm_form_sub")} />

      <div className="form-block">
        <h3>{t("find_field")}</h3>
        <form className="search-row" onSubmit={search}>
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("search_placeholder")} aria-label={t("find_field")} />
          <button className="primary" type="submit" disabled={finding}><Search size={16} /> {t("search")}</button>
          <button className="secondary" type="button" onClick={useGps} disabled={finding}><Crosshair size={16} /> GPS</button>
        </form>
        {findError && <ErrorNote t={t} message={findError} />}
        {results.length > 0 && (
          <ul className="result-list">
            {results.map((r, idx) => (
              <li key={idx}><button type="button" onClick={() => applyPlace(r)}>{r.label || [r.village, r.district, r.state_name].filter(Boolean).join(", ")}</button></li>
            ))}
          </ul>
        )}
        {offices.length > 1 && (
          <label className="field">
            <span>{t("choose_village")}</span>
            <select onChange={(e) => {
              const office = offices[Number(e.target.value)];
              if (office) applyPlace({ ...(place as Place), latitude: office.latitude, longitude: office.longitude, village: office.name });
            }} defaultValue="">
              <option value="" disabled>{t("choose_village")}</option>
              {offices.map((o, idx) => <option key={idx} value={idx}>{o.name}</option>)}
            </select>
          </label>
        )}
        {place && (
          <div className="place-card">
            <CheckCircle2 size={18} />
            <span>{[place.village, place.district, place.state_name, place.country_code].filter(Boolean).join(", ")}</span>
          </div>
        )}
      </div>

      <div className="form-block">
        <h3>{t("draw_field")}</h3>
        <p className="muted">{t("draw_field_help")}</p>
        <FieldMap t={t} center={center} zoom={place ? 17 : 5} corners={corners} onCornersChange={setCorners} />
        <div className="map-toolbar">
          <span>{corners.length >= 3 ? t("field_drawn", { ha: plottedHa.toFixed(2), acres: (plottedHa * 2.47105).toFixed(2) }) : t("corners_count", { n: corners.length })}</span>
          <div>
            <button type="button" className="secondary small" disabled={!corners.length} onClick={() => setCorners(corners.slice(0, -1))}><Undo2 size={14} /> {t("undo")}</button>
            <button type="button" className="secondary small" disabled={!corners.length} onClick={() => setCorners([])}><X size={14} /> {t("clear")}</button>
          </div>
        </div>
        {corners.length < 3 && <p className="hint">{t("no_boundary_hint")}</p>}
      </div>

      <form className="form-block" onSubmit={submit}>
        <h3>{t("farm_details")}</h3>
        <div className="form-grid">
          <label className="field">
            <span>{t("farm_name")}</span>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={t("my_farm")} maxLength={120} />
          </label>
          <label className="field">
            <span>{t("area")}</span>
            <div className="inline-inputs">
              <input type="number" min="0.01" step="0.01" value={form.area_value} onChange={(e) => setForm({ ...form, area_value: e.target.value })} required />
              <select value={form.area_unit} onChange={(e) => setForm({ ...form, area_unit: e.target.value })}>
                <option value="acre">{t("unit_acre")}</option>
                <option value="hectare">{t("unit_hectare")}</option>
              </select>
            </div>
          </label>
        </div>

        <div className="form-section-title">{t("water_source")}</div>
        <div className="chip-group">
          {WATER.map((w) => (
            <button type="button" key={w} className={`chip ${form.water_access === w ? "active" : ""}`} onClick={() => setForm({ ...form, water_access: w })}>
              {t(`water_${w}`)}
            </button>
          ))}
        </div>

        <div className="form-section-title">{t("soil_type")}</div>
        <div className="chip-group">
          {SOILS.map((s) => (
            <button type="button" key={s} className={`chip ${form.soil_type === s ? "active" : ""}`} onClick={() => setForm({ ...form, soil_type: s })}>
              {t(`soil_${s}`)}
            </button>
          ))}
        </div>

        <div className="form-section-title">{t("crop_now")}</div>
        <div className="chip-group">
          {["planning", "planted"].map((s) => (
            <button type="button" key={s} className={`chip ${form.crop_status === s ? "active" : ""}`} onClick={() => setForm({ ...form, crop_status: s })}>
              {t(`crop_status_${s}`)}
            </button>
          ))}
        </div>
        <div className="form-grid">
          {form.crop_status === "planted" && (
            <>
              <label className="field">
                <span>{t("standing_crop")}</span>
                <select value={form.current_crop} onChange={(e) => setForm({ ...form, current_crop: e.target.value })} required>
                  <option value="">{t("select_crop")}</option>
                  {cropOptions}
                </select>
              </label>
              <label className="field">
                <span>{t("sowing_date")}</span>
                <input type="date" value={form.sowing_date} onChange={(e) => setForm({ ...form, sowing_date: e.target.value })} />
              </label>
            </>
          )}
          <label className="field">
            <span>{t("previous_crop")}</span>
            <select value={form.previous_crop} onChange={(e) => setForm({ ...form, previous_crop: e.target.value })}>
              <option value="">{t("previous_none")}</option>
              {cropOptions}
            </select>
          </label>
        </div>

        {saveError && <ErrorNote t={t} message={saveError} />}
        <div className="form-actions">
          <button type="button" className="secondary" onClick={onCancel}>{t("cancel")}</button>
          <button type="submit" className="primary big" disabled={saving}>{saving ? t("saving") : t("save_farm")}</button>
        </div>
      </form>
    </section>
  );
}
