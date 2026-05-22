interface Props {
  onRun: () => void;
  disabled: boolean;
  running: boolean;
}

export default function RunButton({ onRun, disabled, running }: Props) {
  return (
    <button className="primary" onClick={onRun} disabled={disabled}>
      {running ? "Running…" : "Run search"}
    </button>
  );
}
