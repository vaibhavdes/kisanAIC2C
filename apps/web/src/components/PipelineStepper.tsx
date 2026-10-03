import React from "react";
import { Json, TranslationDictionary, View } from "../types";

interface PipelineStepperProps {
  t: TranslationDictionary;
  view: View;
  setView: (v: View) => void;
  farm?: Json;
}

export const PipelineStepper: React.FC<PipelineStepperProps> = ({
  t,
  view,
  setView,
  farm
}) => {
  const stepOrder: View[] = ["farm", "weather", "soil", "crops", "market", "advice"];
  const effectiveIndex = view === "diagnose" ? 6 : stepOrder.indexOf(view);

  return (
    <div className="pipeline-stepper-bar">
      <button
        className={`step-node ${view === "farm" ? "active" : farm ? "done" : ""}`}
        onClick={() => setView("farm")}
      >
        <span className="step-num">1</span>
        <span>{t.step_farm}</span>
      </button>
      <div className={`step-connector ${farm ? "active" : ""}`} />

      <button
        className={`step-node ${
          view === "weather" ? "active" : farm && effectiveIndex > 1 ? "done" : ""
        }`}
        disabled={!farm}
        onClick={() => setView("weather")}
      >
        <span className="step-num">2</span>
        <span>{t.step_weather}</span>
      </button>
      <div
        className={`step-connector ${
          farm && effectiveIndex > 1 ? "active" : ""
        }`}
      />

      <button
        className={`step-node ${
          view === "soil" ? "active" : farm && effectiveIndex > 2 ? "done" : ""
        }`}
        disabled={!farm}
        onClick={() => setView("soil")}
      >
        <span className="step-num">3</span>
        <span>{t.step_soil}</span>
      </button>
      <div
        className={`step-connector ${
          farm && effectiveIndex > 2 ? "active" : ""
        }`}
      />

      <button
        className={`step-node ${
          view === "crops" ? "active" : farm && effectiveIndex > 3 ? "done" : ""
        }`}
        disabled={!farm}
        onClick={() => setView("crops")}
      >
        <span className="step-num">4</span>
        <span>{t.step_crops}</span>
      </button>
      <div
        className={`step-connector ${
          farm && effectiveIndex > 3 ? "active" : ""
        }`}
      />

      <button
        className={`step-node ${view === "market" ? "active" : farm && effectiveIndex > 4 ? "done" : ""}`}
        disabled={!farm}
        onClick={() => setView("market")}
      >
        <span className="step-num">5</span>
        <span>{t.step_market}</span>
      </button>
      <div className={`step-connector ${farm && effectiveIndex > 4 ? "active" : ""}`} />

      <button
        className={`step-node ${view === "advice" ? "active" : farm && effectiveIndex >= 6 ? "done" : ""}`}
        disabled={!farm}
        onClick={() => setView("advice")}
      >
        <span className="step-num">6</span>
        <span>{(t.step_advice_6 || t.step_advice).replace(/^\S+\s/, "")}</span>
      </button>
    </div>
  );
};
