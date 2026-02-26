import type { ConstraintsMeta } from "../types/chat";

type Props = {
  constraints: ConstraintsMeta;
  onRemove: (text: string) => void;
};

function formatTag(key: string, value: unknown): string | null {
  if (value == null) return null;
  if (Array.isArray(value)) {
    if (value.length === 0) return null;
    return value.join(", ");
  }
  return String(value);
}

export default function ConstraintTags({ constraints, onRemove }: Props) {
  const entries = Object.entries(constraints)
    .map(([key, value]) => ({ key, display: formatTag(key, value) }))
    .filter((e): e is { key: string; display: string } => e.display !== null);

  if (entries.length === 0) return null;

  return (
    <div className="sticky top-0 z-10 flex flex-wrap gap-2 border-b border-border bg-surface/90 px-4 py-2 backdrop-blur">
      {entries.map(({ key, display }) => (
        <span
          key={key}
          className="inline-flex items-center gap-1 rounded-full bg-neutral-700 px-2.5 py-1 text-xs text-text"
        >
          {display}
          <button
            onClick={() => onRemove(`remove ${key} filter`)}
            className="ml-0.5 text-muted hover:text-text"
            title={`Remove ${key}`}
          >
            &times;
          </button>
        </span>
      ))}
    </div>
  );
}
