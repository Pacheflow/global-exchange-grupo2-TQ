import { useEffect, useRef, useState } from 'react';

// Equirectangular projection (1000×500): x = (lon+180)/360*1000, y = (90-lat)/180*500
const LANDMASSES = [
  {
    id: 'greenland',
    d: 'M292,22 L312,18 L330,22 L338,38 L332,52 L315,60 L298,56 L288,42 Z',
  },
  {
    id: 'north-america',
    d: 'M112,58 L140,48 L165,48 L210,40 L255,38 L298,46 L316,68 L308,90 L300,110 L294,138 L292,165 L290,240 L292,260 L296,268 L290,272 L285,265 L275,255 L258,248 L245,252 L238,272 L230,294 L236,272 L248,256 L228,232 L215,185 L214,130 L208,105 L192,92 L168,82 L145,92 L125,102 Z',
  },
  {
    id: 'south-america',
    d: 'M268,188 L285,183 L310,188 L332,198 L346,212 L352,235 L360,265 L368,298 L372,325 L368,358 L355,382 L342,405 L326,430 L308,448 L292,450 L278,442 L268,425 L260,395 L256,360 L254,325 L254,292 L257,262 L260,235 L262,212 Z',
  },
  {
    id: 'iceland',
    d: 'M434,52 L442,47 L450,50 L448,62 L440,66 L433,62 Z',
  },
  {
    id: 'uk',
    d: 'M458,78 L462,70 L468,72 L472,82 L468,92 L462,95 L458,88 Z',
  },
  {
    id: 'europe',
    d: 'M452,62 L468,52 L482,54 L498,58 L515,62 L525,76 L524,94 L516,110 L506,120 L498,130 L492,142 L486,138 L478,126 L473,118 L467,124 L460,116 L456,106 L453,92 Z',
  },
  {
    id: 'scandinavia',
    d: 'M490,42 L500,36 L508,40 L514,50 L510,65 L502,78 L494,70 L488,58 Z',
  },
  {
    id: 'africa',
    d: 'M458,175 L470,168 L488,165 L506,168 L518,178 L522,198 L523,222 L520,248 L514,275 L506,302 L495,328 L482,350 L468,362 L456,360 L445,350 L440,328 L437,302 L436,275 L437,248 L440,222 L445,198 L450,180 Z',
  },
  {
    id: 'arabia',
    d: 'M518,162 L536,158 L550,162 L558,175 L555,192 L548,205 L538,208 L528,200 L520,192 L518,178 Z',
  },
  {
    id: 'asia',
    d: 'M522,55 L556,42 L602,38 L650,40 L694,46 L732,55 L758,68 L767,85 L760,105 L746,120 L730,132 L712,140 L694,148 L678,148 L663,155 L648,158 L632,150 L615,148 L600,152 L588,162 L578,165 L568,160 L555,152 L540,140 L528,125 L520,108 L518,85 Z',
  },
  {
    id: 'india',
    d: 'M568,162 L580,165 L590,180 L592,200 L588,218 L582,228 L574,222 L568,206 L565,188 Z',
  },
  {
    id: 'australia',
    d: 'M775,302 L808,292 L835,288 L860,295 L872,310 L874,332 L868,352 L852,368 L830,375 L808,372 L788,362 L774,345 L768,325 Z',
  },
];

const CITIES = [
  { id: 'asu', name: 'Asunción', x: 340, y: 320, primary: true, delay: 500 },
  { id: 'nyc', name: 'Nueva York', x: 294, y: 137, primary: false, delay: 560 },
  { id: 'lon', name: 'Londres', x: 500, y: 107, primary: false, delay: 620 },
  { id: 'sao', name: 'São Paulo', x: 371, y: 315, primary: false, delay: 680 },
  { id: 'bue', name: 'Bs. Aires', x: 338, y: 347, primary: false, delay: 740 },
  { id: 'mad', name: 'Madrid', x: 490, y: 138, primary: false, delay: 800 },
];

const ARCS = [
  { id: 'a1', d: 'M340,320 Q305,155 294,137', stroke: '#4B70FF', glow: 'rgba(75,112,255,0.35)', delay: 850 },
  { id: 'a2', d: 'M340,320 Q415,85 500,107', stroke: '#6888FF', glow: 'rgba(104,136,255,0.28)', delay: 1050 },
  { id: 'a3', d: 'M340,320 Q408,112 490,138', stroke: '#6888FF', glow: 'rgba(104,136,255,0.28)', delay: 1200 },
  { id: 'a4', d: 'M340,320 Q357,285 371,315', stroke: '#22C55E', glow: 'rgba(34,197,94,0.3)', delay: 1350 },
  { id: 'a5', d: 'M340,320 Q322,348 338,347', stroke: '#22C55E', glow: 'rgba(34,197,94,0.3)', delay: 1450 },
];

const CURRENCY_PAIRS = [
  { pair: 'USD / PYG', value: '7.480', change: '+0.42%', trend: 'up' as const,  left: '17%', top: '16%',  delay: 1700 },
  { pair: 'EUR / PYG', value: '8.120', change: '-0.18%', trend: 'down' as const, left: '52%', top: '8%',   delay: 1900 },
  { pair: 'BRL / PYG', value: '1.340', change: '+1.15%', trend: 'up' as const,  left: '40%', top: '53%',  delay: 2100 },
  { pair: 'ARS / PYG', value: '7.40',  change: '-2.30%', trend: 'down' as const, left: '22%', top: '74%',  delay: 2300 },
];

const LAT_LINES = [83, 167, 250, 333, 417];
const LON_LINES = [83, 167, 250, 333, 417, 500, 583, 667, 750, 833, 917];

export interface GlobalExchangeMapProps {
  variant?: 'hero' | 'auth';
  animate?: boolean;
}

export default function GlobalExchangeMap({ variant = 'hero', animate = true }: GlobalExchangeMapProps) {
  const [ready, setReady] = useState(!animate);

  useEffect(() => {
    if (!animate) return;
    const t = setTimeout(() => setReady(true), 80);
    return () => clearTimeout(t);
  }, [animate]);

  const showPairs = variant === 'hero';
  const arcs = variant === 'auth' ? ARCS.slice(0, 3) : ARCS;

  if (!ready) return <div style={{ width: '100%', height: '100%' }} />;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <svg
        viewBox="0 0 1000 500"
        width="100%"
        height="100%"
        style={{ display: 'block', userSelect: 'none', overflow: 'visible' }}
        aria-hidden="true"
      >
        <defs>
          <filter id="gemap-cityglow" x="-150%" y="-150%" width="400%" height="400%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="gemap-asuglow" x="-300%" y="-300%" width="700%" height="700%">
            <feGaussianBlur stdDeviation="8" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="gemap-arcglow" x="-20%" y="-100%" width="140%" height="300%">
            <feGaussianBlur stdDeviation="5" result="blur" />
          </filter>
          <radialGradient id="gemap-coreglow" cx="34%" cy="64%" r="28%">
            <stop offset="0%" stopColor="#1a3280" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#0d1828" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="gemap-arcgrad1" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#3B5BFF" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#22C55E" stopOpacity="0.7" />
          </linearGradient>
          <linearGradient id="gemap-arcgrad2" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#3B5BFF" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#6888FF" stopOpacity="0.6" />
          </linearGradient>
        </defs>

        {/* Graticule */}
        <g opacity="0.05" stroke="#4B70FF" strokeWidth="0.6"
          style={{ animation: 'fadeIn 0.8s ease 0.1s both' }}>
          {LAT_LINES.map(y => <line key={y} x1="0" y1={y} x2="1000" y2={y} />)}
          {LON_LINES.map(x => <line key={x} x1={x} y1="0" x2={x} y2="500" />)}
        </g>

        {/* Ambient glow around Paraguay */}
        <rect width="1000" height="500" fill="url(#gemap-coreglow)"
          style={{ animation: 'fadeIn 1.2s ease 0.3s both', opacity: 0 }} />

        {/* Landmasses */}
        {LANDMASSES.map((land, i) => (
          <path
            key={land.id}
            d={land.d}
            fill="#0C1828"
            stroke="#1C3055"
            strokeWidth="0.7"
            opacity="0"
            style={{ animation: `fadeIn 0.6s ease ${150 + i * 30}ms both` }}
          />
        ))}

        {/* Arc glow layers */}
        {arcs.map(arc => (
          <path
            key={`glow-${arc.id}`}
            d={arc.d}
            fill="none"
            stroke={arc.glow}
            strokeWidth="8"
            strokeLinecap="round"
            filter="url(#gemap-arcglow)"
            opacity="0"
            strokeDasharray="800"
            strokeDashoffset="800"
            style={{
              animation: `fadeIn 0.4s ease ${arc.delay + 50}ms both, drawPath 1.0s cubic-bezier(0.4,0,0.2,1) ${arc.delay + 50}ms both`,
            }}
          />
        ))}

        {/* Arcs */}
        {arcs.map((arc, i) => (
          <path
            key={arc.id}
            d={arc.d}
            fill="none"
            stroke={arc.stroke}
            strokeWidth="1.8"
            strokeLinecap="round"
            opacity="0"
            strokeDasharray="800"
            strokeDashoffset="800"
            style={{
              animation: `fadeIn 0.4s ease ${arc.delay}ms both, drawPath 1.0s cubic-bezier(0.4,0,0.2,1) ${arc.delay}ms both`,
            }}
          >
            {/* flying dot along arc */}
          </path>
        ))}

        {/* Animated travelling dots */}
        {arcs.map((arc, i) => (
          <circle key={`travel-${arc.id}`} r="2.5" fill={arc.stroke} opacity="0.9">
            <animateMotion
              dur="3s"
              begin={`${arc.delay / 1000 + 0.8}s`}
              repeatCount="indefinite"
              path={arc.d}
            />
          </circle>
        ))}

        {/* Cities */}
        {CITIES.map(city => (
          <g key={city.id} filter={city.primary ? 'url(#gemap-asuglow)' : 'url(#gemap-cityglow)'}>
            {city.primary && (
              <>
                <circle cx={city.x} cy={city.y} r={24} fill="none" stroke="#3B5BFF" strokeWidth="0.7"
                  opacity="0"
                  style={{ animation: `fadeIn 0.6s ease ${city.delay + 100}ms both, pulseRing 2.8s ease-out ${city.delay + 100}ms infinite` }} />
                <circle cx={city.x} cy={city.y} r={14} fill="none" stroke="#5B7FFF" strokeWidth="1"
                  opacity="0"
                  style={{ animation: `fadeIn 0.6s ease ${city.delay + 50}ms both, pulseRing 2.8s ease-out ${city.delay + 300}ms infinite` }} />
              </>
            )}
            <circle cx={city.x} cy={city.y} r={city.primary ? 6 : 3.5}
              fill={city.primary ? '#5B7FFF' : '#3B5BFF'}
              opacity="0"
              style={{ animation: `fadeIn 0.5s ease ${city.delay}ms both` }}
            />
            <circle cx={city.x} cy={city.y} r={city.primary ? 2.5 : 1.5}
              fill="#FFFFFF"
              opacity="0"
              style={{ animation: `fadeIn 0.4s ease ${city.delay + 60}ms both` }}
            />
          </g>
        ))}

        {/* City labels */}
        {CITIES.map(city => {
          const below = city.y > 280;
          const isRight = city.x > 400;
          return (
            <text
              key={`lbl-${city.id}`}
              x={city.x + (city.primary ? 0 : isRight ? 7 : -7)}
              y={city.y + (city.primary ? -12 : below ? 16 : -8)}
              textAnchor={city.primary ? 'middle' : isRight ? 'start' : 'end'}
              fill={city.primary ? '#93ACFF' : '#4A6490'}
              fontSize={city.primary ? 10 : 8.5}
              fontFamily="DM Sans, sans-serif"
              fontWeight={city.primary ? '700' : '400'}
              letterSpacing="0.06em"
              opacity="0"
              style={{ animation: `fadeIn 0.5s ease ${city.delay + 200}ms both` }}
            >
              {city.name}
            </text>
          );
        })}
      </svg>

      {/* Currency pair indicators — positioned absolutely over SVG */}
      {showPairs && CURRENCY_PAIRS.map(pair => (
        <div
          key={pair.pair}
          style={{
            position: 'absolute',
            left: pair.left,
            top: pair.top,
            background: 'rgba(6, 11, 28, 0.88)',
            border: `1px solid ${pair.trend === 'up' ? 'rgba(34,197,94,0.35)' : 'rgba(248,113,113,0.35)'}`,
            borderRadius: 8,
            padding: '8px 12px',
            backdropFilter: 'blur(10px)',
            minWidth: 108,
            opacity: 0,
            zIndex: 10,
            pointerEvents: 'none',
            animation: `fadeUp 0.7s cubic-bezier(0.4,0,0.2,1) ${pair.delay}ms both`,
          }}
        >
          <div style={{ fontSize: 9, fontWeight: 700, color: '#3F5C8A', letterSpacing: '0.08em', fontFamily: 'DM Sans', textTransform: 'uppercase' }}>
            {pair.pair}
          </div>
          <div style={{ fontFamily: 'JetBrains Mono', fontWeight: 700, fontSize: 18, color: '#D0E4FF', marginTop: 3, lineHeight: 1, letterSpacing: '-0.01em' }}>
            {pair.value}
          </div>
          <div style={{
            fontSize: 11, fontFamily: 'DM Sans', fontWeight: 600, marginTop: 4,
            display: 'flex', alignItems: 'center', gap: 3,
            color: pair.trend === 'up' ? '#22C55E' : '#F87171',
          }}>
            <span>{pair.trend === 'up' ? '↑' : '↓'}</span>
            {pair.change}
          </div>
        </div>
      ))}
    </div>
  );
}
