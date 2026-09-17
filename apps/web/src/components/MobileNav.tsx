import React from "react";
import { Activity, CloudRain, Leaf, MapPin, Microscope, Sprout } from "lucide-react";
import { Json, View } from "../types";

interface MobileNavProps {
  view: View;
  setView: (v: View) => void;
  farm?: Json;
}

export const MobileNav: React.FC<MobileNavProps> = ({ view, setView, farm }) => {
  return (
    <nav className="mobile-nav">
      <button
        className={view === "home" ? "active" : ""}
        onClick={() => setView("home")}
      >
        <Leaf />
        <span>Home</span>
      </button>
      <button
        className={view === "farm" ? "active" : ""}
        onClick={() => setView("farm")}
      >
        <MapPin />
        <span>Plot</span>
      </button>
      <button
        className={view === "weather" ? "active" : ""}
        disabled={!farm}
        onClick={() => setView("weather")}
      >
        <CloudRain />
        <span>Weather</span>
      </button>
      <button
        className={view === "crops" ? "active" : ""}
        disabled={!farm}
        onClick={() => setView("crops")}
      >
        <Sprout />
        <span>Crops</span>
      </button>
      <button
        className={view === "advice" ? "active" : ""}
        disabled={!farm}
        onClick={() => setView("advice")}
      >
        <Activity />
        <span>Plan</span>
      </button>
      <button
        className={view === "diagnose" ? "active" : ""}
        onClick={() => setView("diagnose")}
      >
        <Microscope />
        <span>Doctor</span>
      </button>
    </nav>
  );
};
