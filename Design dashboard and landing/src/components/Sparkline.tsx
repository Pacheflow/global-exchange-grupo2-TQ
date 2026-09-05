import { useEffect, useId, useRef, useState } from 'react';

interface SparklineProps {
  data: number[];
  trend: 'up' | 'down' | 'neutral';
  width?: number;
  height?: number;
  triggered?: boolean;
  color?: string;
  fluid?: boolean;
  smoothDraw?: boolean;
}

export default function Sparkline({ data, trend, width = 80, height = 32, triggered = true, color, fluid = false, smoothDraw = false }: SparklineProps) {
  const [progress, setProgress] = useState(0);
  const rafRef = useRef<number>(0);
  const instanceId = useId().replace(/:/g, '');

  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    if (!triggered) {
      setProgress(0);
      return;
    }
    setProgress(0);
    const start = performance.now();
    const duration = 1000;
    const animate = (now: number) => {
      const p = Math.min((now - start) / duration, 1);
      setProgress(p);
      if (p < 1) rafRef.current = requestAnimationFrame(animate);
    };
    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [triggered, data]);

  const baseColor =
    trend === 'up' ? '#22C55E' :
    trend === 'down' ? '#F87171' :
    '#5A7AAC';
  const strokeColor = color ?? baseColor;

  if (data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  const points = data.map((v, i) => ({
    x: (i / (data.length - 1)) * width,
    y: height - ((v - min) / range) * (height - 4) - 2,
  }));

  const visibleCount = Math.max(2, Math.round(progress * (points.length - 1)) + 1);
  const visible = points.slice(0, visibleCount);

  const pathD = visible
    .map((p, i) => (i === 0 ? `M${p.x},${p.y}` : `L${p.x},${p.y}`))
    .join(' ');

  const fullPathD = points
    .map((p, i) => (i === 0 ? `M${p.x},${p.y}` : `L${p.x},${p.y}`))
    .join(' ');

  const areaD =
    `M${visible[0].x},${height} ` +
    visible.map(p => `L${p.x},${p.y}`).join(' ') +
    ` L${visible[visible.length - 1].x},${height} Z`;

  const fullAreaD =
    `M${points[0].x},${height} ` +
    points.map(p => `L${p.x},${p.y}`).join(' ') +
    ` L${points[points.length - 1].x},${height} Z`;

  const gradId = `sg-${trend}-${width}-${instanceId}`;
  const clipId = `sg-clip-${instanceId}`;
  const drawProgress = smoothDraw ? 1 - Math.pow(1 - progress, 3) : progress;

  return (
    <svg
      width={fluid ? undefined : width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      overflow="visible"
      style={fluid ? { width: '100%' } : undefined}
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={strokeColor} stopOpacity="0.3" />
          <stop offset="100%" stopColor={strokeColor} stopOpacity="0" />
        </linearGradient>
        {smoothDraw && (
          <clipPath id={clipId}>
            <rect x="0" y="0" width={width * drawProgress} height={height} />
          </clipPath>
        )}
      </defs>
      <g clipPath={smoothDraw ? `url(#${clipId})` : undefined}>
        <path d={smoothDraw ? fullAreaD : areaD} fill={`url(#${gradId})`} />
        <path
          d={smoothDraw ? fullPathD : pathD}
          fill="none"
          stroke={strokeColor}
          strokeWidth={fluid ? 1.8 : 1.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
      {progress >= 1 && (
        <circle
          cx={visible[visible.length - 1].x}
          cy={visible[visible.length - 1].y}
          r={fluid ? 3 : 2.5}
          fill={strokeColor}
        />
      )}
    </svg>
  );
}
