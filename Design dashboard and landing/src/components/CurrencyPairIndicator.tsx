import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { ExchangePair } from "@/data/mapExchangeData";
import AppIcon, { type AppIconName } from "@/components/icons/AppIcon";

export interface CurrencyPairIndicatorProps {
  pair: ExchangePair;
  size?: "sm" | "md";
  active?: boolean;
  dimmed?: boolean;
  onHoverChange?: (hovering: boolean) => void;
  className?: string;
}

const STATUS_COLOR: Record<string, string> = {
  positive: "var(--success)",
  negative: "var(--danger)",
  neutral: "var(--text-2)",
};

const STATUS_ICON: Record<string, AppIconName> = {
  positive: "up",
  negative: "down",
  neutral: "neutral",
};

function useCountUp(value: string, started: boolean, duration = 900) {
  const [display, setDisplay] = useState(value);
  const rafRef = useRef(0);
  const decimals = value.split(".")[1]?.length ?? 0;

  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    if (!started) {
      setDisplay(value);
      return;
    }
    const to = parseFloat(value) || 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - p, 3);
      setDisplay((to * eased).toFixed(decimals));
      if (p < 1) rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, [value, started, duration, decimals]);

  return display;
}

export default function CurrencyPairIndicator({
  pair,
  size = "md",
  active = false,
  dimmed = false,
  onHoverChange,
  className,
}: CurrencyPairIndicatorProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);
  const display = useCountUp(pair.buy, mounted);

  return (
    <div
      className={cn(
        "cursor-default rounded-lg border backdrop-blur-md transition-all duration-300 select-none",
        size === "md" ? "min-w-[106px] px-3 py-2" : "min-w-[92px] px-2.5 py-1.5",
        "border-[var(--border)] bg-[var(--surface)]/80",
        active &&
          "border-[var(--primary)] shadow-[0_0_0_3px_var(--primary-muted)]",
        !active && "shadow-[var(--shadow)]",
        dimmed && "opacity-45",
        className,
      )}
      onMouseEnter={() => onHoverChange?.(true)}
      onMouseLeave={() => onHoverChange?.(false)}
    >
      <div
        className="text-[9px] font-bold uppercase tracking-[0.12em]"
        style={{ color: "var(--text-2)" }}
      >
        {pair.label}
      </div>
      <div
        className="mt-0.5 font-mono text-[16px] leading-none font-bold"
        style={{ color: "var(--text)" }}
      >
        {display}
      </div>
      <div
        className="mt-1 flex items-center gap-1 text-[11px] font-semibold"
        style={{ color: STATUS_COLOR[pair.status] }}
      >
        <AppIcon name={STATUS_ICON[pair.status]} size={12} />
        {pair.change}
      </div>
    </div>
  );
}
