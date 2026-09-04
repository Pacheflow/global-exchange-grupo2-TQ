import { useId } from "react";

interface SparklineProps {
  data: number[];
  positive?: boolean;
  label?: string;
  compact?: boolean;
}

export function Sparkline({
  data,
  positive = true,
  label = "Evolución de la cotización",
  compact = false,
}: SparklineProps) {
  const gradientId = useId().replaceAll(":", "");
  const width = 320;
  const height = compact ? 72 : 96;
  const inset = 4;
  const minimum = Math.min(...data);
  const maximum = Math.max(...data);
  const range = maximum - minimum || 1;
  const points = data.map((value, index) => ({
    x: inset + (index / (data.length - 1)) * (width - inset * 2),
    y: height - inset - ((value - minimum) / range) * (height - inset * 2),
  }));
  const line = points
    .map(({ x, y }, index) => `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`)
    .join(" ");
  const area = `${line} L${points.at(-1)?.x ?? width} ${height} L${points[0]?.x ?? 0} ${height} Z`;
  const color = positive ? "#4f72ff" : "#f87171";

  return (
    <svg
      className="ge-sparkline"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={color} stopOpacity="0.34" />
          <stop offset="1" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path className="ge-sparkline__area" d={area} fill={`url(#${gradientId})`} />
      <path className="ge-sparkline__line" d={line} stroke={color} pathLength="1" />
      <circle cx={points.at(-1)?.x} cy={points.at(-1)?.y} r="3.4" fill={color} />
    </svg>
  );
}
