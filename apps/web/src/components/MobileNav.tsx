import React from "react";
import { Activity, CloudRain, Leaf, Microscope, Sprout } from "lucide-react";
import { Json, T, View } from "../types";

export function MobileNav({ t, view, setView, farm }: { t: T; view: View; setView: (v: View) => void; farm?: Json }) {
  const items: Array<{ view: View; icon: React.ReactNode; key: string; needsFarm: boolean }> = [
    { view: "home", icon: <Leaf />, key: "nav_home", needsFarm: false },
    { view: "weather", icon: <CloudRain />, key: "nav_weather", needsFarm: true },
    { view: "crops", icon: <Sprout />, key: "nav_crops", needsFarm: true },
    { view: "advice", icon: <Activity />, key: "nav_plan", needsFarm: true },
    { view: "diagnose", icon: <Microscope />, key: "nav_doctor", needsFarm: false },
  ];
  return (
    <nav className="mobile-nav" aria-label={t("main_navigation")}>
      {items.map((item) => (
        <button key={item.view} className={view === item.view ? "active" : ""} disabled={item.needsFarm && !farm} onClick={() => setView(item.view)}>
          {item.icon}
          <span>{t(item.key)}</span>
        </button>
      ))}
    </nav>
  );
}
