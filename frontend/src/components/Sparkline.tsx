import { useEffect, useId, useRef, useState } from "react";

interface SparklineProps {
  data: number[];
  trend?: "up" | "down" | "neutral";
  width?: number;
  height?: number;
  triggered?: boolean;
  color?: string;
  fluid?: boolean;
  smoothDraw?: boolean;
  label?: string;
}

export function Sparkline({
  data,
  trend = "up",
  width = 80,
  height = 32,
  triggered = true,
  color,
  fluid = false,
  smoothDraw = false,
  label = "Evolución de la cotización",
}: SparklineProps) {
  const [progress, setProgress] = useState(0);
  const rafRef = useRef(0);
  const instanceId = useId().replace(/:/g, "");

  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    if (!triggered) {
      setProgress(0);
      return;
    }
    setProgress(0);
    const start = performance.now();
    const animate = (now: number) => {
      const next = Math.min((now - start) / 1000, 1);
      setProgress(next);
      if (next < 1) rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [triggered, data]);

  if (data.length < 2) return null;

  const strokeColor = color ?? (trend === "up" ? "#22C55E" : trend === "down" ? "#F87171" : "#5A7AAC");
  const minimum = Math.min(...data);
  const maximum = Math.max(...data);
  const range = maximum - minimum || 1;
  const points = data.map((value, index) => ({
    x: (index / (data.length - 1)) * width,
    y: height - ((value - minimum) / range) * (height - 4) - 2,
  }));
  const visibleCount = Math.max(2, Math.round(progress * (points.length - 1)) + 1);
  const visible = points.slice(0, visibleCount);
  const path = visible.map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`).join(" ");
  const fullPath = points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x},${point.y}`).join(" ");
  const area = `M${visible[0].x},${height} ${visible.map((point) => `L${point.x},${point.y}`).join(" ")} L${visible.at(-1)?.x},${height} Z`;
  const fullArea = `M${points[0].x},${height} ${points.map((point) => `L${point.x},${point.y}`).join(" ")} L${points.at(-1)?.x},${height} Z`;
  const gradientId = `ge-spark-${trend}-${instanceId}`;
  const clipId = `ge-spark-clip-${instanceId}`;
  const drawProgress = smoothDraw ? 1 - Math.pow(1 - progress, 3) : progress;

  return (
    <svg className="ge-sparkline" width={fluid ? undefined : width} height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={label}>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={strokeColor} stopOpacity="0.3" /><stop offset="1" stopColor={strokeColor} stopOpacity="0" /></linearGradient>
        {smoothDraw ? <clipPath id={clipId}><rect width={width * drawProgress} height={height} /></clipPath> : null}
      </defs>
      <g clipPath={smoothDraw ? `url(#${clipId})` : undefined}>
        <path d={smoothDraw ? fullArea : area} fill={`url(#${gradientId})`} />
        <path d={smoothDraw ? fullPath : path} fill="none" stroke={strokeColor} strokeWidth={fluid ? 1.8 : 1.5} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      </g>
      {progress >= 1 ? <circle cx={visible.at(-1)?.x} cy={visible.at(-1)?.y} r={fluid ? 3 : 2.5} fill={strokeColor} /> : null}
    </svg>
  );
}
