import { cn } from "@/lib/utils";

/** Ancho del área cuadrada del globo por variante (mismo tamaño en el mapa
 * real y en el placeholder para que el swap sea invisible). Responsive vía
 * clamp(): vw adapta a la columna y vh evita recortes verticales. */
export const GLOBE_AREA_SIZE: Record<"hero" | "auth", string> = {
  hero: "clamp(520px, min(46vw, calc(100vh - 150px)), 700px)",
  auth: "clamp(420px, 36vw, 580px)",
};

/** Fracción del contenedor que ocupa el globo (resto queda como océano/página). */
export const GLOBE_FRACTION = 0.92;

export type GlobeArtState = "loading" | "fallback";

const DOTS: { x: number; y: number }[] = [
  { x: 58, y: 84 }, // Nueva York
  { x: 142, y: 78 }, // Londres
  { x: 137, y: 92 }, // Madrid
  { x: 86, y: 126 }, // São Paulo
  { x: 72, y: 136 }, // Buenos Aires
];

const SCHEMATIC_ARCS = [
  "M100 108 Q 56 122 58 84",
  "M100 108 Q 140 124 142 78",
  "M100 108 Q 134 120 137 92",
  "M100 108 Q 84 132 86 126",
  "M100 108 Q 74 132 72 136",
];

/** Silueta del globo: rejilla tenue, glow radial, hub con pulse y puntos de
 * destino. Se usa como estado de carga (skeleton) y como fallback si los
 * tiles no pueden cargar: nunca deja la zona del mapa vacía. */
export function GlobeArt({
  state = "loading",
  className,
}: {
  state?: GlobeArtState;
  className?: string;
}) {
  const showArcs = state === "fallback";
  return (
    <div
      className={cn(
        "pointer-events-none absolute inset-0 flex select-none items-center justify-center overflow-hidden",
        className,
      )}
      aria-hidden="true"
    >
      <div
        style={{
          position: "absolute",
          inset: "6%",
          background:
            "radial-gradient(circle at 50% 50%, rgba(59, 91, 255, 0.16), transparent 70%)",
        }}
      />
      <svg
        viewBox="0 0 200 200"
        style={{ width: "100%", height: "100%", position: "relative" }}
      >
        {/* Rejilla de la esfera */}
        <circle
          cx="100"
          cy="100"
          r="86"
          fill="none"
          stroke="var(--border)"
          strokeOpacity="0.5"
          strokeWidth="0.75"
        />
        <circle
          cx="100"
          cy="100"
          r="64"
          fill="none"
          stroke="var(--border)"
          strokeOpacity="0.3"
          strokeWidth="0.6"
        />
        <ellipse
          cx="100"
          cy="100"
          rx="86"
          ry="30"
          fill="none"
          stroke="var(--border)"
          strokeOpacity="0.3"
          strokeWidth="0.6"
        />
        <ellipse
          cx="100"
          cy="100"
          rx="86"
          ry="56"
          fill="none"
          stroke="var(--border)"
          strokeOpacity="0.18"
          strokeWidth="0.6"
        />
        <ellipse
          cx="100"
          cy="100"
          rx="30"
          ry="86"
          fill="none"
          stroke="var(--border)"
          strokeOpacity="0.3"
          strokeWidth="0.6"
        />
        <line
          x1="14"
          y1="100"
          x2="186"
          y2="100"
          stroke="var(--border)"
          strokeOpacity="0.22"
          strokeWidth="0.6"
        />

        {/* Conexiones esquemáticas desde Asunción (solo fallback) */}
        {showArcs && (
          <g
            fill="none"
            stroke="var(--primary)"
            strokeOpacity="0.5"
            strokeWidth="1"
            strokeDasharray="3 3"
            strokeLinecap="round"
          >
            {SCHEMATIC_ARCS.map((d) => (
              <path key={d} d={d} />
            ))}
          </g>
        )}

        {/* Destinos */}
        <g fill="var(--primary-hover)">
          {DOTS.map((d) => (
            <circle
              key={`${d.x}-${d.y}`}
              cx={d.x}
              cy={d.y}
              r={showArcs ? 2.4 : 2}
              opacity={showArcs ? 0.95 : 0.55}
            />
          ))}
        </g>

        {/* Hub: Asunción */}
        <g>
          <circle
            cx="100"
            cy="108"
            r="10"
            fill="none"
            stroke="var(--primary)"
            strokeOpacity="0.35"
            strokeWidth="1"
            className="animate-pulse"
          />
          <circle cx="100" cy="108" r="3" fill="var(--primary)" />
        </g>
      </svg>

      {state === "fallback" && (
        <div
          style={{
            position: "absolute",
            bottom: "5%",
            left: 0,
            right: 0,
            textAlign: "center",
            fontSize: 9,
            color: "var(--text-3)",
            opacity: 0.7,
            letterSpacing: "0.06em",
            fontFamily: "'DM Sans', sans-serif",
          }}
        >
          Mapa temporalmente no disponible
        </div>
      )}
    </div>
  );
}

/** Contenedor del globo con el mismo tamaño que GlobalExchangeMap. Se usa como
 * fallback de Suspense mientras se descarga el chunk del mapa. */
export default function GlobePlaceholder({
  variant = "hero",
  state = "loading",
  className,
}: {
  variant?: "hero" | "auth";
  state?: GlobeArtState;
  className?: string;
}) {
  return (
    <div
      className={cn("relative", className)}
      style={{
        width: GLOBE_AREA_SIZE[variant],
        maxWidth: "100%",
        aspectRatio: "1 / 1",
        margin: "0 auto",
        background: "var(--bg)",
      }}
    >
      <GlobeArt state={state} />
    </div>
  );
}