import type { StepInfo } from "../types";

interface Props {
  steps: StepInfo[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  disabled?: boolean;
}

const ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII"];

export default function StepPicker({
  steps,
  selectedId,
  onSelect,
  disabled,
}: Props) {
  return (
    <div className="lnp-step-grid">
      {steps.map((s) => {
        const selected = s.id === selectedId;
        return (
          <div
            key={s.id}
            className={`lnp-step ${selected ? "selected" : ""}`}
            onClick={() => !disabled && onSelect(s.id)}
            role="radio"
            aria-checked={selected}
          >
            <div className="step-radio" aria-hidden />
            <div className="step-body">
              <div className="step-name">
                <span className="step-num-tag">Stage {ROMAN[s.id]}</span>
                {s.name}
                {s.strict_kinetic && (
                  <span className="kinetic-tag">kinetic required</span>
                )}
              </div>
              <div className="step-desc">{s.description}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
