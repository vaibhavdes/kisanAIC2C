import { useEffect, useState } from "react";
import { IndianRupee, RefreshCw, Users, Store, Calculator, CheckCircle2 } from "lucide-react";
import { api } from "../api";
import { Json, Locale, View } from "../types";

const ACRE = 0.40468564224;
const MONTHS: Record<string, string[]> = {
  "en-IN": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
  "hi-IN": ["जन", "फ़र", "मार्च", "अप्रै", "मई", "जून", "जुला", "अग", "सित", "अक्टू", "नव", "दिस"],
  "mr-IN": ["जाने", "फेब्रु", "मार्च", "एप्रि", "मे", "जून", "जुलै", "ऑग", "सप्टें", "ऑक्टो", "नोव्हें", "डिसें"],
  "te-IN": ["జన", "ఫిబ్ర", "మార్చి", "ఏప్రి", "మే", "జూన్", "జులై", "ఆగ", "సెప్టెం", "అక్టో", "నవం", "డిసెం"],
  "kn-IN": ["ಜನ", "ಫೆಬ್ರ", "ಮಾರ್ಚ್", "ಏಪ್ರಿ", "ಮೇ", "ಜೂನ್", "ಜುಲೈ", "ಆಗ", "ಸೆಪ್ಟೆಂ", "ಅಕ್ಟೋ", "ನವೆಂ", "ಡಿಸೆಂ"],
};

const rs = (v?: number | null) => (v == null ? "—" : `₹${Math.round(v).toLocaleString("en-IN")}`);
const pct = (v?: number | null) => (v == null ? "—" : `${v > 0 ? "+" : ""}${Math.round(v * 100)}%`);
const fill = (s: string, vars: Record<string, string | number>) => Object.entries(vars).reduce((acc, [k, v]) => acc.split(`{${k}}`).join(String(v)), s || "");

export interface MarketViewProps {
  t: Record<string, string>;
  locale: Locale;
  farm?: Json;
  season: string;
  cropRecs: Json | null;
  initialCrop?: string;
  go: (v: View) => void;
}

/** Single-series bar chart of harvest prices with an MSP reference line; hover shows the value. */
function PriceBars({ past, msp, t }: { past: Json[]; msp?: number | null; t: Record<string, string> }) {
  const rows = [...past].reverse();
  const max = Math.max(...rows.map(r => r.price), msp || 0) * 1.1 || 1;
  const w = 320, h = 150, pad = 26, bw = (w - pad) / Math.max(rows.length, 1);
  return (
    <svg viewBox={`0 0 ${w} ${h + 22}`} className="mk-chart" role="img" aria-label={t.market_past_prices}>
      <line x1={pad} x2={w} y1={h} y2={h} className="mk-axis" />
      {rows.map((r, i) => {
        const bh = (r.price / max) * (h - 10);
        return (
          <g key={r.label}>
            <rect x={pad + i * bw + bw * 0.2} y={h - bh} width={bw * 0.6} height={bh} rx={4} className="mk-bar">
              <title>{`${r.label}: ${rs(r.price)}/qtl${r.msp ? ` · MSP ${rs(r.msp)}` : ""}`}</title>
            </rect>
            <text x={pad + i * bw + bw / 2} y={h - bh - 4} className="mk-val">{Math.round(r.price / 100) / 10}k</text>
            <text x={pad + i * bw + bw / 2} y={h + 14} className="mk-lbl">{r.label.replace(/^(Kharif|Rabi|Summer) /, "")}</text>
          </g>
        );
      })}
      {msp ? <line x1={pad} x2={w} y1={h - (msp / max) * (h - 10)} y2={h - (msp / max) * (h - 10)} className="mk-msp" /> : null}
    </svg>
  );
}

/** Monthly district price (line) with the harvest-time forecast as a shaded band and a point. */
function TrendChart({ recent, price, locale, t }: { recent: Json[]; price: Json; locale: Locale; t: Record<string, string> }) {
  const names = MONTHS[locale] || MONTHS["en-IN"];
  const sell: string[] = price.sell_months || [];
  const idx = (m: string) => Number(m.slice(0, 4)) * 12 + Number(m.slice(5)) - 1;
  if (!recent.length || !sell.length) return null;
  const start = idx(recent[0].month), end = Math.max(idx(sell[sell.length - 1]), idx(recent[recent.length - 1].month));
  const w = 340, h = 150, left = 34, bottom = 18;
  const vals = [...recent.map(r => r.price), price.low, price.high, price.msp || 0].filter(Boolean);
  const max = Math.max(...vals) * 1.08, min = Math.min(...vals) * 0.85;
  const x = (m: string) => left + ((idx(m) - start) / Math.max(1, end - start)) * (w - left - 6);
  const y = (v: number) => (h - bottom) - ((v - min) / (max - min)) * (h - bottom - 8);
  // A month with no mandi data breaks the line rather than being drawn across.
  const path = recent.map((r, i) => `${i && idx(r.month) - idx(recent[i - 1].month) === 1 ? "L" : "M"}${x(r.month).toFixed(1)},${y(r.price).toFixed(1)}`).join(" ");
  const x0 = x(sell[0]) - 4, x1 = x(sell[sell.length - 1]) + 4;
  const ticks = recent.filter(r => r.month.endsWith("-01")).map(r => r.month);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mk-chart" role="img" aria-label={t.market_trend}>
      {[min, (min + max) / 2, max].map(v => (
        <g key={v}><line x1={left} x2={w} y1={y(v)} y2={y(v)} className="mk-gridline" /><text x={left - 4} y={y(v) + 3} className="mk-lbl end">{Math.round(v / 100) / 10}k</text></g>
      ))}
      {price.msp ? <line x1={left} x2={w} y1={y(price.msp)} y2={y(price.msp)} className="mk-msp" /> : null}
      <rect x={x0} width={x1 - x0} y={y(price.high)} height={Math.max(2, y(price.low) - y(price.high))} rx={4} className="mk-band">
        <title>{`${t.market_expected_price}: ${rs(price.expected)} (${rs(price.low)} – ${rs(price.high)})`}</title>
      </rect>
      <path d={path} className="mk-line" />
      {recent.map(r => <circle key={r.month} cx={x(r.month)} cy={y(r.price)} r={6} className="mk-hit"><title>{`${names[Number(r.month.slice(5)) - 1]} ${r.month.slice(0, 4)}: ${rs(r.price)}`}</title></circle>)}
      <circle cx={(x0 + x1) / 2} cy={y(price.expected)} r={4.5} className="mk-dot" />
      {ticks.map(m => <text key={m} x={x(m)} y={h - 4} className="mk-lbl">{m.slice(0, 4)}</text>)}
    </svg>
  );
}

function MonthProfile({ profile, best, locale }: { profile: Json[]; best?: number; locale: Locale }) {
  const names = MONTHS[locale] || MONTHS["en-IN"];
  const w = 320, h = 90;
  const vals = profile.map(p => p.index);
  const min = Math.min(...vals) - 0.1, max = Math.max(...vals);
  const bw = w / 12;
  return (
    <svg viewBox={`0 0 ${w} ${h + 16}`} className="mk-chart">
      {profile.map(p => {
        const y = h - ((p.index - min) / (max - min)) * (h - 8);
        return (
          <g key={p.month}>
            <rect x={(p.month - 1) * bw + bw * 0.2} y={y} width={bw * 0.6} height={h - y} rx={3} className={p.month === best ? "mk-bar best" : "mk-bar soft"}>
              <title>{`${names[p.month - 1]}: ${pct(p.index - 1)}`}</title>
            </rect>
            <text x={(p.month - 1) * bw + bw / 2} y={h + 12} className="mk-lbl">{names[p.month - 1]}</text>
          </g>
        );
      })}
    </svg>
  );
}

function Histogram({ bins, t }: { bins: Json[]; t: Record<string, string> }) {
  const w = 320, h = 80, max = Math.max(...bins.map(b => b.share)) || 1, bw = w / bins.length;
  return (
    <svg viewBox={`0 0 ${w} ${h + 16}`} className="mk-chart" aria-label={t.market_profit_dist}>
      {bins.map((b, i) => {
        const bh = (b.share / max) * h;
        return (
          <rect key={i} x={i * bw + 1} y={h - bh} width={bw - 2} height={bh} rx={2} className={b.to <= 0 ? "mk-bar loss" : "mk-bar"}>
            <title>{`${rs(b.from)} – ${rs(b.to)}: ${Math.round(b.share * 100)}%`}</title>
          </rect>
        );
      })}
      <text x={0} y={h + 13} className="mk-lbl start">{rs(bins[0]?.from)}</text>
      <text x={w} y={h + 13} className="mk-lbl end">{rs(bins[bins.length - 1]?.to)}</text>
    </svg>
  );
}

export function MarketView({ t, locale, farm, season, cropRecs, initialCrop, go }: MarketViewProps) {
  const crops: Json[] = (cropRecs?.recommendations as Json[]) || [];
  const [crop, setCrop] = useState<string>(initialCrop || crops[0]?.crop || "");
  const [lookback, setLookback] = useState(3);
  const [outlook, setOutlook] = useState<Json | null>(null);
  const [mix, setMix] = useState<Json | null>(null);
  const [loading, setLoading] = useState(false);
  const [sim, setSim] = useState<Json | null>(null);
  const [simBusy, setSimBusy] = useState(false);
  const [planMsg, setPlanMsg] = useState("");
  const [inputs, setInputs] = useState({ acres: "", price: "", cost: "", yieldQ: "", msp: false });

  useEffect(() => { if (!crop && crops[0]) setCrop(crops[0].crop); }, [cropRecs]);
  useEffect(() => { if (initialCrop) setCrop(initialCrop); }, [initialCrop]);

  useEffect(() => {
    if (!farm || !crop) return;
    setLoading(true); setSim(null); setPlanMsg("");
    Promise.all([
      api<Json>(`/api/v1/farms/${farm.id}/market/outlook?crop=${crop}&season=${season}&lookback=${lookback}`),
      api<Json>(`/api/v1/farms/${farm.id}/regional-crop-mix?season=${season}`),
    ]).then(([o, x]) => { setOutlook(o); setMix(x); }).catch(e => setOutlook({ error: (e as Error).message })).finally(() => setLoading(false));
  }, [farm?.id, crop, season, lookback]);

  if (!farm) return null;

  const runSim = async () => {
    setSimBusy(true);
    try {
      const num = (v: string) => (v.trim() ? Number(v) : null);
      const res = await api<Json>(`/api/v1/farms/${farm.id}/market/simulate`, {
        method: "POST",
        body: JSON.stringify({
          crop, season, lookback, locale,
          area_ha: num(inputs.acres) ? Number(inputs.acres) * ACRE : null,
          price_override: num(inputs.price),
          cost_per_ha_override: num(inputs.cost) != null ? Number(inputs.cost) / ACRE : null,
          yield_override_kg_ha: num(inputs.yieldQ) != null ? (Number(inputs.yieldQ) * 100) / ACRE : null,
          use_msp_floor: inputs.msp,
        }),
      });
      setSim(res.simulation);
    } catch (e) { alert((e as Error).message); } finally { setSimBusy(false); }
  };

  const savePlan = async () => {
    try {
      await api(`/api/v1/farms/${farm.id}/crop-plan`, { method: "POST", body: JSON.stringify({ crop, season }) });
      setPlanMsg(t.market_plan_saved);
      setMix(await api<Json>(`/api/v1/farms/${farm.id}/regional-crop-mix?season=${season}`));
      const o = await api<Json>(`/api/v1/farms/${farm.id}/market/outlook?crop=${crop}&season=${season}&lookback=${lookback}`);
      setOutlook(o);
    } catch (e) { alert((e as Error).message); }
  };

  const allCrops: Json[] = [...crops, ...((cropRecs?.unsuitable_crops as Json[]) || [])];
  const nameOf = (c: string) => (allCrops.find(x => x.crop === c)?.crop_name as string) || c.replace("_", " ");
  const s = sim || outlook?.simulation;
  const price = outlook?.price;
  const crowd = outlook?.crowding;
  const y = outlook?.yield, cost = outlook?.cost;
  const isFrp = price?.basis === "frp";
  const names = MONTHS[locale] || MONTHS["en-IN"];
  const sellMonths = (price?.sell_months || []).map((m: string) => names[Number(m.slice(5)) - 1]).join(", ");
  const perAcre = (v?: number | null) => (v == null || !s ? null : v / (s.area_ha / ACRE));

  return (
    <section className="panel">
      <div className="section-title">
        <IndianRupee />
        <div>
          <small>{farm.name} · {farm.taluka ? `${farm.taluka}, ` : ""}{farm.district}</small>
          <h2>{t.market_title}</h2>
        </div>
      </div>
      <p className="mk-sub">{t.market_sub}</p>

      <div className="mk-controls">
        <label>{t.market_pick_crop}
          <select value={crop} onChange={e => setCrop(e.target.value)}>
            {crops.map(c => <option key={c.crop} value={c.crop}>{c.crop_name}</option>)}
          </select>
        </label>
        <label>{t.market_lookback}
          <select value={lookback} onChange={e => setLookback(Number(e.target.value))}>
            {[1, 3, 5].map(n => <option key={n} value={n}>{fill(t.market_seasons, { n })}</option>)}
          </select>
        </label>
      </div>

      {loading && <div className="mk-loading"><RefreshCw className="spin" size={20} /></div>}
      {!loading && outlook?.error && <div className="notice error">{outlook.error}</div>}
      {!loading && outlook && outlook.covered === false && (
        <div className="notice">{fill(t.market_not_covered, { districts: (outlook.covered_districts || []).map((d: string) => d[0].toUpperCase() + d.slice(1)).join(", ") })}</div>
      )}
      {!loading && outlook?.covered && !price && <div className="notice">{t.market_no_data}</div>}

      {!loading && outlook?.covered && price && (
        <>
          <div className="mk-grid">
            <div className="mk-card mk-hero">
              <small>{isFrp ? t.market_frp : t.market_expected_price}</small>
              <div className="mk-big">{rs(price.expected)}<span>{t.market_per_qtl}</span></div>
              {!isFrp && <div className="mk-muted">{fill(t.market_range, { low: rs(price.low), high: rs(price.high) })}</div>}
              <div className="mk-row"><span>{t.market_sell_in}</span><b>{sellMonths}</b></div>
              {price.past?.[0] && <div className="mk-row"><span>{t.market_last_season} ({price.past[0].label})</span><b>{rs(price.past[0].price)}</b></div>}
              {price.msp && !isFrp && <div className="mk-row"><span>{t.market_msp}</span><b>{rs(price.msp)}</b></div>}
              {price.below_msp_seasons > 0 && <div className="mk-warn">{fill(t.market_below_msp, { n: price.below_msp_seasons, m: price.past.length })}</div>}
              {outlook.live && (
                <div className="mk-live">● {t.market_live_now}: <b>{rs(outlook.live.median_rs_qtl)}</b>
                  <small> ({outlook.live.month ? `${names[Number(outlook.live.month.slice(5)) - 1]} ${outlook.live.month.slice(0, 4)} · AGMARKNET` : fill(t.market_live_detail, { n: outlook.live.reports, d: outlook.live.days })})</small>
                </div>
              )}
            </div>

            {!isFrp && outlook.recent_prices?.length > 6 && (
              <div className="mk-card">
                <h4>{t.market_trend}</h4>
                <div className="mk-legend"><i className="mk-legend-line" /> {t.market_trend_line} <i className="mk-legend-band" /> {t.market_trend_band}{price.msp && <><i className="mk-legend-msp" /> {t.market_msp}</>}</div>
                <TrendChart recent={outlook.recent_prices} price={price} locale={locale} t={t} />
              </div>
            )}

            {!isFrp && price.past?.length > 0 && (
              <div className="mk-card">
                <h4>{t.market_past_prices}</h4>
                {price.msp && <div className="mk-legend"><i className="mk-legend-msp" /> {t.market_msp} {rs(price.msp)}</div>}
                <PriceBars past={price.past} msp={price.msp} t={t} />
              </div>
            )}

            <div className={`mk-card mk-crowd ${crowd?.level}`}>
              <h4><Users size={16} /> {t.market_crowding}</h4>
              <div className="mk-badge">{t[`market_crowd_${crowd?.level}`]}</div>
              {crowd?.village_farms >= 3 && <p>{fill(t.market_crowd_village, { same: crowd.village_same_crop, total: crowd.village_farms, village: crowd.village })}</p>}
              {crowd?.taluka_farms >= 3 && <p>{fill(t.market_crowd_taluka, { same: crowd.taluka_same_crop, total: crowd.taluka_farms, taluka: crowd.taluka })}</p>}
              {crowd?.district_farms > 0 && <p>{fill(t.market_crowd_district, { same: crowd.district_same_crop, total: crowd.district_farms, district: farm.district })}
                {crowd.sample_entries > 0 && <small> ({fill(t.market_crowd_sample, { n: crowd.sample_entries })})</small>}</p>}
              {crowd?.apy_trend && <p>{fill(t.market_crowd_apy, { year: `${crowd.apy_trend.latest_year}-${String(crowd.apy_trend.latest_year + 1).slice(2)}`, area: Math.round(crowd.apy_trend.area_ha).toLocaleString("en-IN"), change: pct(crowd.apy_trend.change) })}</p>}
              {!isFrp && price.base_before_crowding && <p className="mk-muted">{fill(t.market_crowd_effect, { effect: pct(price.expected / price.base_before_crowding - 1) })}</p>}
              {mix && Object.keys(mix.district_counts || {}).length > 0 && (
                <div className="mk-mix">
                  {Object.entries(mix.district_counts as Record<string, number>).slice(0, 6).map(([c, n]) => (
                    <div key={c} className={c === crop ? "on" : ""}><span>{nameOf(c)}</span><i style={{ width: `${(n / mix.district_farms) * 100}%` }} /><b>{n}</b></div>
                  ))}
                </div>
              )}
              {mix?.my_plan?.crop === crop
                ? <div className="mk-ok"><CheckCircle2 size={14} /> {t.market_plan_saved}</div>
                : <button className="secondary" onClick={savePlan}>{t.market_plan_btn}</button>}
              {planMsg && mix?.my_plan?.crop !== crop && <div className="mk-ok">{planMsg}</div>}
            </div>

            {outlook.monthly_profile?.length > 6 && outlook.storable && (
              <div className="mk-card">
                <h4>{t.market_month_profile}</h4>
                <MonthProfile profile={outlook.monthly_profile} best={outlook.best_sell?.month} locale={locale} />
                {outlook.best_sell && outlook.best_sell.gain_vs_harvest > 0.03 && (
                  <p className="mk-muted">{fill(t.market_best_month, { month: names[outlook.best_sell.month - 1], gain: pct(outlook.best_sell.gain_vs_harvest) })}</p>
                )}
              </div>
            )}

            {outlook.apmcs?.length > 0 && (
              <div className="mk-card">
                <h4><Store size={16} /> {t.market_apmc}</h4>
                <table className="mk-table">
                  <thead><tr><th></th><th>{t.market_apmc_price}</th><th>{t.market_apmc_arrivals}</th><th>{t.market_apmc_distance}</th></tr></thead>
                  <tbody>
                    {outlook.apmcs.slice(0, 8).map((a: Json) => (
                      <tr key={a.market} className={a.is_local ? "on" : ""}>
                        <td>{a.market}</td><td>{rs(a.price)}</td>
                        <td>{a.arrivals_t != null ? `${Math.round(a.arrivals_t).toLocaleString("en-IN")} t` : "—"}{a.arrivals_change != null && <small> {pct(a.arrivals_change)}</small>}</td>
                        <td>{a.distance_km != null ? `${a.distance_km} km` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <small className="mk-muted">{outlook.apmcs[0]?.season}</small>
              </div>
            )}
          </div>

          <div className="mk-card mk-sim">
            <h4><Calculator size={16} /> {t.market_sim_title}</h4>
            <p className="mk-muted">{fill(t.market_sim_sub, { runs: s?.runs || 2000 })}</p>
            <div className="mk-inputs">
              <label>{t.market_area} ({t.market_acres})<input type="number" min="0" step="0.1" placeholder={(farm.area_ha / ACRE).toFixed(2)} value={inputs.acres} onChange={e => setInputs({ ...inputs, acres: e.target.value })} /></label>
              <label>{t.market_price_override}<input type="number" min="0" placeholder={String(price.expected)} value={inputs.price} onChange={e => setInputs({ ...inputs, price: e.target.value })} /></label>
              <label>{t.market_cost_override}<input type="number" min="0" placeholder={cost?.rs_ha ? String(Math.round(cost.rs_ha * ACRE)) : t.market_auto} value={inputs.cost} onChange={e => setInputs({ ...inputs, cost: e.target.value })} /></label>
              <label>{t.market_yield_override}<input type="number" min="0" step="0.1" placeholder={y ? ((y.kg_ha * ACRE) / 100).toFixed(1) : t.market_auto} value={inputs.yieldQ} onChange={e => setInputs({ ...inputs, yieldQ: e.target.value })} /></label>
              {price.msp && !isFrp && <label className="mk-check"><input type="checkbox" checked={inputs.msp} onChange={e => setInputs({ ...inputs, msp: e.target.checked })} />{t.market_msp_toggle}</label>}
              <button className="primary" onClick={runSim} disabled={simBusy}>{simBusy ? <RefreshCw size={14} className="spin" /> : null} {t.market_run}</button>
            </div>

            {s && (
              <>
                <table className="mk-table mk-results">
                  <thead><tr><th></th><th>{t.market_low}</th><th>{t.market_typical}</th><th>{t.market_high}</th></tr></thead>
                  <tbody>
                    <tr><td>{t.market_production}</td><td>{s.production_qtl.p10} {t.market_qtl}</td><td>{s.production_qtl.p50} {t.market_qtl}</td><td>{s.production_qtl.p90} {t.market_qtl}</td></tr>
                    <tr><td>{t.market_revenue}</td><td>{rs(s.revenue_rs.p10)}</td><td>{rs(s.revenue_rs.p50)}</td><td>{rs(s.revenue_rs.p90)}</td></tr>
                    <tr><td>{t.market_cost}</td><td colSpan={3}>{rs(s.cost_rs)}</td></tr>
                    {s.profit_rs && <tr className="mk-profit"><td>{t.market_profit}</td>
                      {(["p10", "p50", "p90"] as const).map(k => <td key={k} className={s.profit_rs[k] < 0 ? "neg" : "pos"}>{rs(s.profit_rs[k])}</td>)}</tr>}
                  </tbody>
                </table>
                <div className="mk-kpis">
                  {s.loss_probability != null && <div><small>{t.market_loss_chance}</small><b className={s.loss_probability > 0.3 ? "neg" : ""}>{Math.round(s.loss_probability * 100)}%</b></div>}
                  {s.breakeven_price_rs_qtl && <div><small>{t.market_breakeven}</small><b>{rs(s.breakeven_price_rs_qtl)}{t.market_per_qtl}</b></div>}
                  {s.profit_rs && <div><small>{t.market_profit_per_acre}</small><b>{rs(perAcre(s.profit_rs.p50))}</b></div>}
                  {s.transport_rs_qtl > 0 && <div><small>{t.market_transport}</small><b>{rs(s.transport_rs_qtl)}{t.market_per_qtl}</b></div>}
                </div>
                {s.histogram && <><h5>{t.market_profit_dist}</h5><Histogram bins={s.histogram} t={t} /></>}
              </>
            )}

            <details className="mk-details">
              <summary>{t.market_assumptions}</summary>
              {!isFrp && <p>{fill(t.market_model_note, { infl: Math.round((price.inflation_per_year || 0.04) * 100), flex: Math.abs(Math.round((price.flexibility?.value || 0) * 10)) })}</p>}
              {y && <p>{fill(t.market_yield_basis, { y: ((y.kg_ha * ACRE) / 100).toFixed(1), source: y.source })}{y.estimate && <em> ({t.market_estimate})</em>}</p>}
              {cost && <p>{fill(t.market_cost_basis, { c: Math.round(cost.rs_ha * ACRE).toLocaleString("en-IN"), basis: cost.basis })}{cost.estimate && <em> ({t.market_estimate})</em>}</p>}
              <h5>{t.market_sources}</h5>
              <ul>{(outlook.sources || []).map((src: Json) => <li key={src.name}>{src.url ? <a href={src.url} target="_blank" rel="noreferrer">{src.name}</a> : src.name} — {src.detail}</li>)}</ul>
            </details>
          </div>
        </>
      )}

      <div className="pipeline-footer-nav">
        <button className="nav-prev-btn" onClick={() => go("crops")}>{t.btn_back_crops}</button>
        <button className="nav-next-btn" onClick={() => go("advice")}>{t.btn_proceed_plan}</button>
      </div>
    </section>
  );
}
