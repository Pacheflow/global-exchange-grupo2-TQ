import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { Map as MapLibreMap } from "maplibre-gl";
import {
  Map as MapCanvas,
  MapArc,
  MapMarker,
  MapPopup,
  MarkerContent,
  MarkerLabel,
  useMap,
  type MapArcDatum,
} from "@/components/ui/map";
import { cn } from "@/lib/utils";
import CurrencyPairIndicator from "@/components/CurrencyPairIndicator";
import ExchangePairPopup from "@/components/map/ExchangePairPopup";
import {
  GlobeArt,
  GLOBE_AREA_SIZE,
  GLOBE_FRACTION,
} from "@/components/map/GlobePlaceholder";
import { globalExchangeMapStyles } from "@/components/map/globalExchangeMapStyles";
import {
  HUB,
  DESTINATIONS,
  ARC_CONFIG,
  PAIR_TO_CITY,
  exchangePairs,
  HERO_CITY_IDS,
  AUTH_CITY_IDS,
  AUTH_VISIBLE_PAIRS,
  type PairCode,
  type ExchangePair,
} from "@/data/mapExchangeData";

export interface GlobalExchangeMapProps {
  variant?: "hero" | "auth";
  animate?: boolean;
}

type ArcDatum = MapArcDatum & {
  color: string;
  width: number;
  opacity: number;
  pairCode: PairCode;
};

const ARC_BASE_COLOR = "#3B5BFF";
const ARC_ACTIVE_COLOR = "#6B8AFF";

const GLOBE_PROJECTION = { type: "globe" } as const;
const HUB_CENTER: [number, number] = [HUB.longitude, HUB.latitude];

// Contador de instancias (dev): si sube por encima de 1 en una sesión, el
// mapa se está remontando y MapLibre se reinicializa innecesariamente.
let MOUNT_COUNT = 0;

const CITY_BY_ID = new Map(DESTINATIONS.map((c) => [c.id, c] as const));

// Estable en superficie: no se recrea en cada render.
const HERO_CITIES = DESTINATIONS.filter((c) =>
  (HERO_CITY_IDS as readonly string[]).includes(c.id),
);
const AUTH_CITIES = DESTINATIONS.filter((c) =>
  (AUTH_CITY_IDS as readonly string[]).includes(c.id),
);
const ALL_PAIRS = exchangePairs;
const AUTH_PAIRS = exchangePairs.filter((p) =>
  (AUTH_VISIBLE_PAIRS as readonly PairCode[]).includes(p.code),
);

const VARIANT_CONFIG = {
  hero: {
    areaSize: GLOBE_AREA_SIZE.hero,
    indicatorSize: "md" as const,
    cities: HERO_CITIES,
    pairs: ALL_PAIRS,
    defaultEarth: 600,
  },
  auth: {
    areaSize: GLOBE_AREA_SIZE.auth,
    indicatorSize: "sm" as const,
    cities: AUTH_CITIES,
    pairs: AUTH_PAIRS,
    defaultEarth: 480,
  },
};

// Posiciones que asocian cada par a su zona geográfica real (Norteamérica,
// Europa, Brasil, Argentina), pegadas al borde del globo.
const PAIR_POSITIONS: Record<PairCode, { left: string; top: string }> = {
  USD: { left: "3%", top: "4%" },
  EUR: { left: "62%", top: "3%" },
  BRL: { left: "58%", top: "61%" },
  ARS: { left: "5%", top: "67%" },
};

const INDICATOR_DELAY_BASE = 740;
const INDICATOR_DELAY_STEP = 120;

type OverlayState = "on" | "fading" | "off" | "failed";

function makeArcDatum(
  city: (typeof DESTINATIONS)[number],
  activePair: PairCode | null,
): ArcDatum {
  const cfg = ARC_CONFIG[city.id];
  const emphasized = activePair === city.pairCode;
  const related = activePair == null || emphasized;
  return {
    id: `arc-${city.id}`,
    from: HUB_CENTER,
    to: [city.longitude, city.latitude],
    pairCode: city.pairCode,
    color: emphasized ? ARC_ACTIVE_COLOR : ARC_BASE_COLOR,
    width:
      activePair == null ? cfg.width : emphasized ? cfg.width + 0.8 : cfg.width * 0.85,
    opacity: related ? cfg.opacity : 0.28,
  };
}

/** Puente MapCN → React: reporta cuándo el mapa quedó listo y errores de
 * tiles/estilo (solo durante la carga inicial). */
function MapLoadBridge({
  onLoaded,
  onError,
}: {
  onLoaded: () => void;
  onError: () => void;
}) {
  const { map, isLoaded } = useMap();
  const onLoadedRef = useRef(onLoaded);
  const onErrorRef = useRef(onError);
  onLoadedRef.current = onLoaded;
  onErrorRef.current = onError;

  useEffect(() => {
    if (isLoaded) onLoadedRef.current();
  }, [isLoaded]);

  useEffect(() => {
    if (!map) return;
    const handleError = () => onErrorRef.current();
    map.on("error", handleError);
    return () => {
      map.off("error", handleError);
    };
  }, [map]);

  return null;
}

export default function GlobalExchangeMap({
  variant = "hero",
  animate = true,
}: GlobalExchangeMapProps) {
  const theme = "dark" as const;
  const config = VARIANT_CONFIG[variant];
  const cities = config.cities;
  const pairs = config.pairs;

  const [phase, setPhase] = useState(animate ? 0 : 4);
  const [hoverPair, setHoverPair] = useState<PairCode | null>(null);
  const [pinnedPair, setPinnedPair] = useState<PairCode | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const [overlay, setOverlay] = useState<OverlayState>("on");

  const areaRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const loadedRef = useRef(false);
  const boxWidthRef = useRef(0);
  const fitRafRef = useRef(0);

  // Métricas de desarrollo (solo en modo dev).
  const renderCountRef = useRef(0);
  const mountedAtRef = useRef(performance.now());
  renderCountRef.current += 1;

  useEffect(() => {
    if (import.meta.env.DEV) {
      MOUNT_COUNT += 1;
      console.info(
        `[GlobalExchangeMap] mount #${MOUNT_COUNT} at ${(performance.now() / 1000).toFixed(2)}s`,
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Animación visual por fases (independiente de la carga técnica).
  useEffect(() => {
    if (!animate) {
      setPhase(4);
      return;
    }
    const t1 = setTimeout(() => setPhase(1), 120); // Asunción
    const t2 = setTimeout(() => setPhase(2), 300); // destinos
    const t3 = setTimeout(() => setPhase(3), 520); // arcos
    const t4 = setTimeout(() => setPhase(4), 740); // pares cambiarios
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
      clearTimeout(t4);
    };
  }, [animate]);

  const handleMapLoaded = useCallback(() => {
    if (loadedRef.current) return;
    loadedRef.current = true;
    setMapLoaded(true);
    if (import.meta.env.DEV) {
      console.info(
        `[GlobalExchangeMap] tiles listos en ${(performance.now() - mountedAtRef.current).toFixed(0)} ms · renders: ${renderCountRef.current}`,
      );
    }
    fitGlobeRef.current?.();
  }, []);

  const handleMapError = useCallback(() => {
    if (!loadedRef.current) setOverlay("failed");
  }, []);

  // Crossfade: al cargar, desvanece el skeleton sobre el mapa real (150–300ms).
  useEffect(() => {
    if (!mapLoaded || overlay !== "on") return;
    setOverlay("fading");
    const t = setTimeout(() => setOverlay("off"), 320);
    return () => clearTimeout(t);
  }, [mapLoaded, overlay]);

  // Fallback si los tiles no llegan: mantiene la silueta del globo con sus
  // conexiones + mensaje discreto, sin dejar la zona vacía.
  useEffect(() => {
    if (mapLoaded || overlay === "failed") return;
    const t = setTimeout(() => {
      if (!loadedRef.current) setOverlay("failed");
    }, 12000);
    return () => clearTimeout(t);
  }, [mapLoaded, overlay]);

  // Ajusta el zoom para que el mundo completo quepa en el contenedor real
  // (cámara intacta: sin "zoom excesivo" en la cartografía, solo encaje).
  const fitGlobeRef = useRef<() => void>(() => {});
  const fitGlobe = useCallback(() => {
    const map = mapRef.current;
    const width = boxWidthRef.current;
    if (!map || width <= 0) return;
    const zoom = Math.log2((width * GLOBE_FRACTION) / 512);
    cancelAnimationFrame(fitRafRef.current);
    fitRafRef.current = requestAnimationFrame(() => {
      try {
        map.jumpTo({ center: HUB_CENTER, zoom, bearing: 0, pitch: 0 });
      } catch {
        // mapa aún inicializando
      }
    });
  }, []);
  fitGlobeRef.current = fitGlobe;

  useEffect(() => {
    const el = areaRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect?.width ?? 0;
      if (w <= 0 || Math.abs(w - boxWidthRef.current) < 6) return;
      boxWidthRef.current = w;
      fitGlobeRef.current();
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      cancelAnimationFrame(fitRafRef.current);
    };
  }, []);

  const activePair = hoverPair ?? pinnedPair;

  const arcData = useMemo(
    () => cities.map((city) => makeArcDatum(city, activePair)),
    [cities, activePair],
  );

  const activePairData: ExchangePair | undefined = activePair
    ? exchangePairs.find((p) => p.code === activePair)
    : undefined;

  const popupCity = activePairData
    ? CITY_BY_ID.get(PAIR_TO_CITY[activePairData.code])
    : undefined;

  const initialZoom = Math.log2((config.defaultEarth * GLOBE_FRACTION) / 512);
  const indicatorIndex = useMemo(
    () => new Map(pairs.map((p) => [p.code, pairs.indexOf(p)])),
    [pairs],
  );

  const overlayVisible =
    overlay === "on" || overlay === "fading" || overlay === "failed";

  return (
    <div
      ref={areaRef}
      style={{
        width: config.areaSize,
        maxWidth: "100%",
        aspectRatio: "1 / 1",
        position: "relative",
        margin: "0 auto",
        background: "var(--bg)",
      }}
    >
      <MapCanvas
        ref={mapRef}
        className="animate-fade-in"
        theme={theme}
        styles={globalExchangeMapStyles}
        projection={GLOBE_PROJECTION}
        center={HUB_CENTER}
        zoom={initialZoom}
        bearing={0}
        pitch={0}
        minZoom={-1}
        maxZoom={4}
        maxPitch={45}
        dragPan
        dragRotate
        scrollZoom={false}
        touchZoomRotate={false}
        doubleClickZoom={false}
        boxZoom={false}
        keyboard={false}
      >
        <MapLoadBridge
          onLoaded={handleMapLoaded}
          onError={handleMapError}
        />

        {variant === "hero" && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              zIndex: 0,
              pointerEvents: "none",
              background:
                "radial-gradient(46% 46% at 50% 50%, rgba(59, 91, 255, 0.12), transparent 72%)",
            }}
          />
        )}

        {phase >= 3 && (
          <MapArc<ArcDatum>
            data={arcData}
            samples={80}
            paint={{
              "line-color": ["get", "color"] as never,
              "line-width": ["+", ["get", "width"], 3] as never,
              "line-opacity": ["*", ["get", "opacity"], 0.22] as never,
              "line-blur": 1.5,
            }}
            interactive={false}
          />
        )}
        {phase >= 3 && (
          <MapArc<ArcDatum>
            data={arcData}
            samples={80}
            paint={{
              "line-color": ["get", "color"] as never,
              "line-width": ["get", "width"] as never,
              "line-opacity": ["get", "opacity"] as never,
            }}
            onHover={(e) => setHoverPair(e ? e.arc.pairCode : null)}
            onClick={(e) =>
              setPinnedPair((p) => (p === e.arc.pairCode ? null : e.arc.pairCode))
            }
          />
        )}

        {phase >= 1 && (
          <MapMarker longitude={HUB.longitude} latitude={HUB.latitude}>
            <MarkerContent className="grid size-7 place-items-center">
              <span className="bg-[#3B5BFF]/15 absolute size-7 animate-pulse rounded-full" />
              <span className="absolute -inset-1 rounded-full border border-[#3B5BFF]/25" />
              <span className="relative size-2.5 rounded-full border-2 border-[#3B5BFF] bg-[#DCE8FF] shadow-[0_0_10px_rgba(59,91,255,0.8)]" />
            </MarkerContent>
            <MarkerLabel
              position="bottom"
              className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--text-2)]"
            >
              Asunción
            </MarkerLabel>
          </MapMarker>
        )}

        {phase >= 2 &&
          cities.map((city) => {
            const isActive = activePair === city.pairCode;
            return (
              <MapMarker
                key={city.id}
                longitude={city.longitude}
                latitude={city.latitude}
                onMouseEnter={() => setHoverPair(city.pairCode)}
                onMouseLeave={() => setHoverPair(null)}
              >
                <MarkerContent
                  className={cn(
                    "animate-fade-in grid size-3 place-items-center",
                    isActive && "scale-125",
                  )}
                >
                  <span
                    className={cn(
                      "size-2 rounded-full border transition-all duration-200",
                      isActive
                        ? "scale-125 border-white bg-[#6B8AFF] shadow-[0_0_9px_rgba(107,138,255,0.85)]"
                        : "border-white/60 bg-[#3B5BFF]",
                    )}
                  />
                </MarkerContent>
                <MarkerLabel
                  position="top"
                  className={cn(
                    "animate-fade-in text-[9px] font-medium text-[var(--text-2)]",
                    isActive && "font-semibold text-[var(--primary-hover)]",
                  )}
                >
                  {city.name}
                </MarkerLabel>
              </MapMarker>
            );
          })}

        {activePairData && popupCity && (
          <MapPopup
            key={activePairData.code}
            longitude={popupCity.longitude}
            latitude={popupCity.latitude}
            className="border-[var(--border)] bg-[var(--surface)] p-0 text-[var(--text)] shadow-[var(--shadow-lg)]"
          >
            <ExchangePairPopup pair={activePairData} />
          </MapPopup>
        )}
      </MapCanvas>

      {/* Skeleton del globo: tapa el mapa mientras carga y hace crossfade.
          En fallback permanece con sus conexiones esquemáticas. */}
      {overlayVisible && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 20,
            background: "var(--bg)",
            opacity: overlay === "fading" ? 0 : 1,
            transition: "opacity 320ms ease",
            pointerEvents:
              overlay === "fading" || overlay === "failed" ? "none" : "auto",
          }}
        >
          <GlobeArt state={overlay === "failed" ? "fallback" : "loading"} />
        </div>
      )}

      {phase >= 4 &&
        pairs.map((pair) => {
          const pos = PAIR_POSITIONS[pair.code];
          const isActive = activePair === pair.code;
          const idx = indicatorIndex.get(pair.code) ?? 0;
          return (
            <div
              key={pair.code}
              className="animate-fade-up"
              style={{
                position: "absolute",
                left: pos.left,
                top: pos.top,
                zIndex: 10,
                animationDelay: `${
                  INDICATOR_DELAY_BASE + idx * INDICATOR_DELAY_STEP
                }ms`,
              }}
            >
              <CurrencyPairIndicator
                pair={pair}
                size={config.indicatorSize}
                active={isActive}
                dimmed={activePair != null && !isActive}
                onHoverChange={(h) => setHoverPair(h ? pair.code : null)}
              />
            </div>
          );
        })}
    </div>
  );
}
