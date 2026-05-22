interface Props {
  quant: string[];
  kinetic: string[];
  signal: string[];
}

interface GroupProps {
  label: string;
  items: string[];
  cls: string;
}

function Group({ label, items, cls }: GroupProps) {
  if (items.length === 0) return null;
  return (
    <>
      <div className="chip-group-label">{label}</div>
      <div className="chips">
        {items.map((t, i) => (
          <span key={`${cls}-${i}`} className={`chip ${cls}`}>{t}</span>
        ))}
      </div>
    </>
  );
}

export default function MatchedTerms({ quant, kinetic, signal }: Props) {
  if (quant.length + kinetic.length + signal.length === 0) return null;
  return (
    <>
      <Group label="Quantitative evidence" items={quant} cls="chip-quant" />
      <Group label="Kinetic evidence" items={kinetic} cls="chip-kinetic" />
      <Group label="Signal phrases" items={signal} cls="chip-signal" />
    </>
  );
}
