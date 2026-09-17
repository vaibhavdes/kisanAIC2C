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
  const stepOrder: View[] = ["farm", "weather", "soil", "crops", "advice"];
  const currentIndex = stepOrder.indexOf(view);

  return (
    <div className="pipeline-stepper-bar">
      <button
        className={`step-node ${view === "farm" ? "active" : farm ? "done" : ""}`}
        onClick={() => setView("farm")}
      >
        <span className="step-num">1</span>
        <span>{t.step_farm || "1. Field Plot"}</span>
      </button>
      <div className={`step-connector ${farm ? "active" : ""}`} />

      <button
        className={`step-node ${
          view === "weather" ? "active" : farm && currentIndex > 1 ? "done" : ""
        }`}
        disabled={!farm}
        onClick={() => setView("weather")}
      >
        <span className="step-num">2</span>
        <span>{t.step_weather || "2. Local Weather"}</span>
      </button>
      <div
        className={`step-connector ${
          farm && currentIndex > 1 ? "active" : ""
        }`}
      />

      <button
        className={`step-node ${
          view === "soil" ? "active" : farm && currentIndex > 2 ? "done" : ""
        }`}
        disabled={!farm}
        onClick={() => setView("soil")}
      >
        <span className="step-num">3</span>
        <span>{t.step_soil || "3. Soil Health"}</span>
      </button>
      <div
        className={`step-connector ${
          farm && currentIndex > 2 ? "active" : ""
        }`}
      />

      <button
        className={`step-node ${
          view === "crops" ? "active" : farm && currentIndex > 3 ? "done" : ""
        }`}
        disabled={!farm}
        onClick={() => setView("crops")}
      >
        <span className="step-num">4</span>
        <span>{t.step_crops || "4. Crop Recs"}</span>
      </button>
      <div
        className={`step-connector ${
          farm && currentIndex > 3 ? "active" : ""
        }`}
      />

      <button
        className={`step-node ${view === "advice" ? "active" : ""}`}
        disabled={!farm}
        onClick={() => setView("advice")}
      >
        <span className="step-num">5</span>
        <span>{t.step_advice || "5. Field Plan"}</span>
      </button>
    </div>
  );
};
