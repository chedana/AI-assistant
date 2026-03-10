import type { CompareData, CompareListingData } from "../types/chat";

type Props = {
  data: CompareData;
};

type FieldDef = {
  key: keyof CompareListingData;
  label: string;
  format: (v: unknown) => string;
  bestFn?: "min" | "max";
};

const FIELDS: FieldDef[] = [
  { key: "price_pcm", label: "Price/mo", format: v => v ? `£${Number(v).toLocaleString()}` : "—", bestFn: "min" },
  { key: "bedrooms", label: "Beds", format: v => (v && Number(v) > 0) ? String(Number(v)) : "—", bestFn: "max" },
  { key: "bathrooms", label: "Baths", format: v => (v && Number(v) > 0) ? String(Number(v)) : "—", bestFn: "max" },
  { key: "deposit", label: "Deposit", format: v => v ? `£${Number(v).toLocaleString()}` : "—", bestFn: "min" },
  { key: "available_from", label: "Available", format: v => (v && String(v).trim()) ? String(v) : "—" },
  { key: "size_sqm", label: "Size", format: v => v ? `${Number(v)} sqm` : "—", bestFn: "max" },
  { key: "furnish_type", label: "Furnished", format: v => (v && String(v).trim()) ? String(v) : "—" },
  { key: "property_type", label: "Type", format: v => (v && String(v).trim()) ? String(v) : "—" },
];

function findBest(listings: CompareListingData[], key: keyof CompareListingData, mode: "min" | "max"): number | null {
  let bestIdx: number | null = null;
  let bestVal: number | null = null;
  for (let i = 0; i < listings.length; i++) {
    const raw = listings[i][key];
    const n = Number(raw);
    if (!n || isNaN(n)) continue;
    if (bestVal === null || (mode === "min" ? n < bestVal : n > bestVal)) {
      bestVal = n;
      bestIdx = i;
    }
  }
  return bestIdx;
}

export default function CompareTable({ data }: Props) {
  const { listings } = data;
  if (listings.length < 2) return null;

  // Pre-compute best indices per field
  const bestMap = new Map<string, number | null>();
  for (const f of FIELDS) {
    if (f.bestFn) {
      bestMap.set(f.key, findBest(listings, f.key, f.bestFn));
    }
  }

  return (
    <div className="compare-table-wrapper overflow-x-auto rounded-lg border border-border">
      <table className="compare-table w-full text-sm">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-panel px-3 py-2 text-left text-xs text-muted">
              Field
            </th>
            {listings.map((l) => (
              <th key={l.index} className="px-3 py-2 text-left">
                <a
                  href={l.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs font-medium text-[#7dd3fc] underline hover:opacity-80"
                >
                  #{l.index} — {l.title.length > 24 ? l.title.slice(0, 24) + "…" : l.title}
                </a>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {FIELDS.map((f) => (
            <tr key={f.key}>
              <td className="sticky left-0 z-10 bg-[#262626] px-3 py-2 text-xs font-medium text-muted">
                {f.label}
              </td>
              {listings.map((l, i) => {
                const isBest = bestMap.get(f.key) === i;
                return (
                  <td
                    key={l.index}
                    className={`px-3 py-2 text-xs ${
                      isBest ? "font-semibold text-accent" : "text-text"
                    }`}
                  >
                    {f.format(l[f.key])}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
