import { useEffect, useRef, useState } from 'react';

interface SparklineProps {
  data: number[];
  trend: 'up' | 'down' | 'neutral';
  width?: number;
  height?: number;
  triggered?: boolean;
}

export default function Sparkline({ data, trend, width = 80, height = 32, triggered = true }: SparklineProps) {
  const [progress, setProgress] = useState(0);
  const rafRef = useRef<number>(0);

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

  const color =
    trend === 'up' ? '#22C55E' :
    trend === 'down' ? '#F87171' :
    '#5A7AAC';

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

  const areaD =
    `M${visible[0].x},${height} ` +
    visible.map(p => `L${p.x},${p.y}`).join(' ') +
    ` L${visible[visible.length - 1].x},${height} Z`;

  const gradId = `sg-${trend}-${width}`;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} overflow="visible">
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaD} fill={`url(#${gradId})`} />
      <path
        d={pathD}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {progress >= 1 && (
        <circle
          cx={visible[visible.length - 1].x}
          cy={visible[visible.length - 1].y}
          r="2.5"
          fill={color}
        />
      )}
    </svg>
  );
}
