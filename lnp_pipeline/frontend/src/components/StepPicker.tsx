import type { StepInfo } from "../types";

interface Props {
  steps: StepInfo[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  disabled?: boolean;
}

const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII"];

export default function StepPicker({ steps, selectedId, onSelect, disabled }: Props) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Step 1 · Select an LNP journey stage</h2>
        <span className="step-label">single-select per run</span>
      </div>
      <div className="steps">
        {steps.map((s) => {
          const selected = s.id === selectedId;
          return (
            <label
              key={s.id}
              className={`step ${selected ? "selected" : ""}`}
              onClick={() => !disabled && onSelect(s.id)}
            >
              <input
                type="radio"
                name="step"
                checked={selected}
                onChange={() => onSelect(s.id)}
                disabled={disabled}
              />
              <div>
                <div className="name">
                  <span className="step-number">{ROMAN[s.id]}.</span> {s.name}
                </div>
                <div className="desc">{s.description}</div>
              </div>
            </label>
          );
        })}
      </div>
    </div>
  );
}
