import { useEffect, useState } from 'react';

const CX = 400, CY = 270, R = 228;

const cities = [
  { id: 'asu', name: 'Asunción', x: 373, y: 403, primary: true },
  { id: 'nyc', name: 'Nueva York', x: 329, y: 150 },
  { id: 'sao', name: 'São Paulo', x: 413, y: 397 },
  { id: 'bue', name: 'Buenos Aires', x: 372, y: 431 },
  { id: 'lon', name: 'Londres', x: 510, y: 109 },
  { id: 'mia', name: 'Miami', x: 296, y: 202 },
  { id: 'mad', name: 'Madrid', x: 526, y: 144 },
];

const connections = [
  { from: 'asu', to: 'nyc', d: 'M373,403 Q320,270 329,150' },
  { from: 'asu', to: 'sao', d: 'M373,403 Q393,400 413,397' },
  { from: 'nyc', to: 'lon', d: 'M329,150 Q420,80 510,109' },
  { from: 'mia', to: 'mad', d: 'M296,202 Q400,65 526,144' },
  { from: 'bue', to: 'lon', d: 'M372,431 Q480,300 510,109' },
];

const latLines = [
  { cy: 145, rx: 115, ry: 14 },
  { cy: 210, rx: 199, ry: 28 },
  { cy: 270, rx: 228, ry: 38 },
  { cy: 330, rx: 199, ry: 28 },
  { cy: 395, rx: 115, ry: 14 },
];

const lonAngles = [0, 20, 40, 60, 80, 100, 120, 140, 160];

export default function WorldMap({ animate = true }: { animate?: boolean }) {
  const [drawn, setDrawn] = useState(false);

  useEffect(() => {
    if (!animate) { setDrawn(true); return; }
    const t = setTimeout(() => setDrawn(true), 400);
    return () => clearTimeout(t);
  }, [animate]);

  return (
    <svg
      viewBox="0 0 800 560"
      width="100%"
      height="100%"
      style={{ userSelect: 'none' }}
      aria-hidden="true"
    >
      <defs>
        <clipPath id="globeClip">
          <circle cx={CX} cy={CY} r={R} />
        </clipPath>
        <radialGradient id="globeBg" cx="42%" cy="38%" r="65%">
          <stop offset="0%" stopColor="#0D2060" />
          <stop offset="60%" stopColor="#060E2E" />
          <stop offset="100%" stopColor="#030812" />
        </radialGradient>
        <radialGradient id="globeGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#2040B0" stopOpacity="0.25" />
          <stop offset="100%" stopColor="#2040B0" stopOpacity="0" />
        </radialGradient>
        <filter id="cityGlow" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="softGlow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="8" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <linearGradient id="connGrad1" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0%" stopColor="#3B5BFF" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#22C55E" stopOpacity="0.7" />
        </linearGradient>
        <linearGradient id="connGrad2" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#3B5BFF" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#5B80FF" stopOpacity="0.5" />
        </linearGradient>
      </defs>

      {/* Outer ambient glow */}
      <circle cx={CX} cy={CY} r={R + 40} fill="url(#globeGlow)" />

      {/* Globe background */}
      <circle cx={CX} cy={CY} r={R} fill="url(#globeBg)" />

      {/* Grid lines */}
      <g clipPath="url(#globeClip)" opacity="0.28">
        {latLines.map((l, i) => (
          <ellipse
            key={`lat-${i}`}
            cx={CX} cy={l.cy}
            rx={l.rx} ry={l.ry}
            fill="none"
            stroke="#3050C0"
            strokeWidth="0.6"
          />
        ))}
        {lonAngles.map((angle, i) => (
          <ellipse
            key={`lon-${i}`}
            cx={CX} cy={CY}
            rx={18} ry={R}
            fill="none"
            stroke="#3050C0"
            strokeWidth="0.6"
            transform={`rotate(${angle}, ${CX}, ${CY})`}
          />
        ))}
      </g>

      {/* Subtle continent fills */}
      <g clipPath="url(#globeClip)" opacity="0.12">
        {/* North America */}
        <ellipse cx={285} cy={195} rx={60} ry={75} fill="#4060E0" />
        {/* South America */}
        <ellipse cx={375} cy={390} rx={38} ry={60} fill="#4060E0" />
        {/* Europe */}
        <ellipse cx={495} cy={148} rx={30} ry={38} fill="#4060E0" />
        {/* Africa (partially visible) */}
        <ellipse cx={510} cy={260} rx={28} ry={55} fill="#4060E0" />
      </g>

      {/* Connection arcs */}
      {drawn && connections.map((conn, i) => {
        const totalLen = 300;
        return (
          <path
            key={conn.from + conn.to}
            d={conn.d}
            fill="none"
            stroke={i < 2 ? 'url(#connGrad1)' : 'url(#connGrad2)'}
            strokeWidth={i < 2 ? 1.5 : 1}
            strokeLinecap="round"
            strokeDasharray={totalLen}
            strokeDashoffset={totalLen}
            opacity="0.8"
            style={{
              animation: `drawPath 1.2s cubic-bezier(0.4,0,0.2,1) ${0.3 + i * 0.2}s both`,
            }}
          />
        );
      })}

      {/* City dots */}
      {cities.map((city, i) => (
        <g key={city.id} filter="url(#cityGlow)">
          {city.primary && drawn && (
            <>
              <circle cx={city.x} cy={city.y} r={10} fill="none" stroke="#3B5BFF" strokeWidth="1.2"
                opacity="0" style={{ animation: `pulseRing 2s ease-out ${0.8}s infinite` }} />
              <circle cx={city.x} cy={city.y} r={16} fill="none" stroke="#3B5BFF" strokeWidth="0.6"
                opacity="0" style={{ animation: `pulseRing2 2s ease-out ${0.8}s infinite` }} />
            </>
          )}
          <circle
            cx={city.x} cy={city.y}
            r={city.primary ? 5 : 3.5}
            fill={city.primary ? '#5B7FFF' : '#3B5BFF'}
            opacity="0"
            style={{
              animation: `fadeIn 0.4s ease ${0.6 + i * 0.1}s both`,
            }}
          />
          <circle
            cx={city.x} cy={city.y}
            r={city.primary ? 2.5 : 1.5}
            fill="#FFFFFF"
            opacity="0"
            style={{
              animation: `fadeIn 0.4s ease ${0.65 + i * 0.1}s both`,
            }}
          />
        </g>
      ))}

      {/* City labels */}
      {drawn && (
        <g style={{ animation: 'fadeIn 0.6s ease 1.2s both', opacity: 0 }}>
          {cities.filter(c => c.primary || ['nyc', 'lon', 'mia'].includes(c.id)).map(city => (
            <text
              key={`label-${city.id}`}
              x={city.x + (city.x > CX ? 8 : -8)}
              y={city.y + (city.y > CY ? 14 : -8)}
              textAnchor={city.x > CX ? 'start' : 'end'}
              fill="#8BA8E0"
              fontSize="9"
              fontFamily="DM Sans, sans-serif"
              fontWeight="500"
              letterSpacing="0.04em"
            >
              {city.name}
            </text>
          ))}
        </g>
      )}

      {/* Globe border ring */}
      <circle cx={CX} cy={CY} r={R} fill="none" stroke="#1E3A80" strokeWidth="1" />
      <circle cx={CX} cy={CY} r={R - 1} fill="none" stroke="rgba(100,140,255,0.15)" strokeWidth="0.5" />
    </svg>
  );
}
