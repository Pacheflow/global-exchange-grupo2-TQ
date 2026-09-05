import type { StyleSpecification } from "maplibre-gl";

export type GEMapTheme = "dark" | "light";

interface GEMapThemeColors {
  ocean: string;
  land: string;
  boundary: string;
  boundaryOpacity: number;
  label: string;
  labelOpacity: number;
  sky: string;
}

// Palette Global Exchange — océano = fondo del sitio para fundir mapa y página.
const DARK: GEMapThemeColors = {
  ocean: "#060B1E",
  land: "#0E1A3A",
  boundary: "#2C4380",
  boundaryOpacity: 0.35,
  label: "#6A89C0",
  labelOpacity: 0.22,
  sky: "#060B1E",
};

const LIGHT: GEMapThemeColors = {
  ocean: "#F0F5FF",
  land: "#DCE8FB",
  boundary: "#A9BEE8",
  boundaryOpacity: 0.55,
  label: "#6A89C0",
  labelOpacity: 0.4,
  sky: "#F0F5FF",
};

const CARTO_TILES =
  "https://tiles.basemaps.cartocdn.com/vector/carto.streets/v1/tiles.json";
const CARTO_GLYPHS =
  "https://tiles.basemaps.cartocdn.com/fonts/{fontstack}/{range}.pbf";
const CARTO_ATTRIBUTION = "© OpenStreetMap contributors © CARTO";

export function createGlobalExchangeStyle(
  theme: GEMapTheme,
): StyleSpecification {
  const c = theme === "dark" ? DARK : LIGHT;

  return {
    version: 8,
    name: `Global Exchange · ${theme}`,
    projection: { type: "globe" },
    glyphs: CARTO_GLYPHS,
    sources: {
      carto: {
        type: "vector",
        url: CARTO_TILES,
        attribution: CARTO_ATTRIBUTION,
      },
    },
    sky: {
      "sky-color": c.sky,
      "horizon-color": c.sky,
      "sky-horizon-blend": 0.4,
      "fog-color": c.sky,
      "fog-ground-blend": 0.3,
    },
    layers: [
      // Masa terrestre (el océano se pinta encima con los polígonos de agua).
      {
        id: "ge-land",
        type: "background",
        paint: { "background-color": c.land },
      },
      // Océanos del mismo color que el fondo del sitio.
      {
        id: "ge-water",
        type: "fill",
        source: "carto",
        "source-layer": "water",
        paint: { "fill-color": c.ocean, "fill-opacity": 1 },
      },
      // Fronteras de países: extremadamente sutiles.
      {
        id: "ge-boundary",
        type: "line",
        source: "carto",
        "source-layer": "boundary",
        minzoom: 0,
        filter: ["all", ["==", "admin_level", 2], ["==", "maritime", 0]],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": c.boundary,
          "line-opacity": c.boundaryOpacity,
          "line-width": ["interpolate", ["linear"], ["zoom"], 0, 0.7, 6, 1.1],
        },
      },
      // Únicamente nombres de países: pequeños y de baja opacidad. Sin
      // continentes, ciudades, rutas ni POIs para que no dominen.
      {
        id: "ge-country-labels",
        type: "symbol",
        source: "carto",
        "source-layer": "place",
        minzoom: 0,
        maxzoom: 7,
        filter: ["==", "class", "country"],
        layout: {
          "text-field": ["get", "name_en"],
          "text-size": [
            "interpolate",
            ["linear"],
            ["zoom"],
            0,
            7.5,
            4,
            9,
          ],
          "text-transform": "uppercase",
          "text-letter-spacing": 0.14,
          "text-font": ["Noto Sans Regular"],
        },
        paint: {
          "text-color": c.label,
          "text-opacity": c.labelOpacity,
          "text-halo-color": c.ocean,
          "text-halo-width": 1.2,
        },
      },
    ],
  };
}

export const globalExchangeMapStyles = {
  dark: createGlobalExchangeStyle("dark"),
  light: createGlobalExchangeStyle("light"),
};