import React from "react";
import { Activity, CloudRain, Leaf, MapPin, Microscope, Sprout } from "lucide-react";
import { Json, View } from "../types";

interface MobileNavProps {
  t: Record<string, string>;
  view: View;
  setView: (v: View) => void;
  farm?: Json;
}

export const MobileNav: React.FC<MobileNavProps> = ({ t, view, setView, farm }) => {
  return (
    <nav className="mobile-nav">
      <button
        className={view === "home" ? "active" : ""}
        onClick={() => setView("home")}
      >
        <Leaf />
        <span>{t.nav_home}</span>
      </button>
      <button
        className={view === "farm" ? "active" : ""}
        onClick={() => setView("farm")}
      >
        <MapPin />
        <span>{t.nav_farm}</span>
      </button>
      <button
        className={view === "weather" ? "active" : ""}
        disabled={!farm}
        onClick={() => setView("weather")}
      >
        <CloudRain />
        <span>{t.nav_weather}</span>
      </button>
      <button
        className={view === "crops" ? "active" : ""}
        disabled={!farm}
        onClick={() => setView("crops")}
      >
        <Sprout />
        <span>{t.nav_crops}</span>
      </button>
      <button
        className={view === "advice" ? "active" : ""}
        disabled={!farm}
        onClick={() => setView("advice")}
      >
        <Activity />
        <span>{t.nav_plan}</span>
      </button>
      <button
        className={view === "diagnose" ? "active" : ""}
        onClick={() => setView("diagnose")}
      >
        <Microscope />
        <span>{t.nav_doctor}</span>
      </button>
    </nav>
  );
};
