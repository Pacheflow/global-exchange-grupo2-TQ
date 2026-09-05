import type { ExchangePair } from "@/data/mapExchangeData";
import AppIcon from "@/components/icons/AppIcon";

interface PairRowProps {
  label: string;
  value: string;
}

function PairRow({ label, value }: PairRowProps) {
  return (
    <div>
      <div
        className="text-[9px] uppercase tracking-[0.1em]"
        style={{ color: "var(--text-3)" }}
      >
        {label}
      </div>
      <div
        className="mt-0.5 font-mono text-[13px] font-bold"
        style={{ color: "var(--text)" }}
      >
        {value}
      </div>
    </div>
  );
}

export default function ExchangePairPopup({ pair }: { pair: ExchangePair }) {
  const trendColor =
    pair.status === "positive"
      ? "var(--success)"
      : pair.status === "negative"
        ? "var(--danger)"
        : "var(--text-2)";
  const trendIcon = pair.status === "positive" ? "up" : pair.status === "negative" ? "down" : "neutral";

  return (
    <div className="w-44" style={{ fontFamily: "'DM Sans', sans-serif" }}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <span
          className="text-[10px] font-bold uppercase tracking-[0.12em]"
          style={{ color: "var(--text-2)" }}
        >
          {pair.label}
        </span>
        <span
          className="flex items-center gap-0.5 text-[10px] font-semibold"
          style={{ color: trendColor }}
        >
          <AppIcon name={trendIcon} size={12} /> {pair.change}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <PairRow label="Compra" value={pair.buy} />
        <PairRow label="Venta" value={pair.sell} />
      </div>
      <div
        className="mt-2 border-t pt-1.5 text-[10px]"
        style={{ borderColor: "var(--border)", color: "var(--text-3)" }}
      >
        Última actualización · {pair.updated}
      </div>
    </div>
  );
}
