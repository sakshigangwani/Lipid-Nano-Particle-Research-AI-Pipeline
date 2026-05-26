interface Props {
  onRun: () => void;
  disabled: boolean;
  running: boolean;
}

export default function RunButton({ onRun, disabled, running }: Props) {
  return (
    <button className="btn btn-primary" onClick={onRun} disabled={disabled}>
      {running ? (
        <>
          <span className="spinner" /> Running…
        </>
      ) : (
        <>
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.35-4.35" />
          </svg>
          Run search
        </>
      )}
    </button>
  );
}
