import React from "react";
import { Json, T, View } from "../types";

const STEPS: Array<{ view: View; key: string }> = [
  { view: "farm", key: "step_farm" },
  { view: "weather", key: "step_weather" },
  { view: "soil", key: "step_soil" },
  { view: "crops", key: "step_crops" },
  { view: "advice", key: "step_plan" },
];

export function PipelineStepper({ t, view, setView, farm }: { t: T; view: View; setView: (v: View) => void; farm?: Json }) {
  const current = STEPS.findIndex((step) => step.view === view);
  return (
    <nav className="pipeline-stepper-bar" aria-label={t("steps")}>
      {STEPS.map((step, idx) => (
        <React.Fragment key={step.view}>
          {idx > 0 && <div className={`step-connector ${farm && idx <= current ? "active" : ""}`} />}
          <button
            className={`step-node ${view === step.view ? "active" : farm && idx < current ? "done" : ""}`}
            disabled={!farm && step.view !== "farm"}
            onClick={() => setView(step.view)}
            aria-current={view === step.view ? "step" : undefined}
          >
            <span className="step-num">{idx + 1}</span>
            <span>{t(step.key)}</span>
          </button>
        </React.Fragment>
      ))}
    </nav>
  );
}
