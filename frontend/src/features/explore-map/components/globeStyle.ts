import type { ExpressionSpecification, StyleSpecification } from 'maplibre-gl';

// Screen approximation of RAL 5019; all terrain tones stay in the Capri Blue family.
export const globePalette = {
  capri: '#005e83', land: '#9abac8', water: '#084b68',
  outline: '#d6eaf1', outlineHalo: '#123f54',
  fire: '#f26450', fireCore: '#c83532',
};

// Data-driven colour keeps this fully opaque fill in the ordered translucent
// pass. A constant opaque fill is drawn too early: heatmaps ignore its depth.
const waterColor: ExpressionSpecification = ['match', ['get', 'class'], 'ocean', globePalette.water, '#105772'];

export const globeStyle: StyleSpecification = {
  version: 8,
  projection: { type: 'globe' },
  sky: {
    'sky-color': '#f6f6f3', 'horizon-color': '#c6dce5',
    'fog-color': '#f6f6f3', 'sky-horizon-blend': 0.4,
    'atmosphere-blend': 0.35,
  },
  sources: {
    geography: {
      type: 'vector', url: 'https://tiles.openfreemap.org/planet',
      attribution: '<a href="https://openfreemap.org/">OpenFreeMap</a> © <a href="https://openmaptiles.org/">OpenMapTiles</a> © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    },
    relief: {
      type: 'raster', tileSize: 256,
      tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
      attribution: 'Imagery © Esri, Maxar, Earthstar Geographics',
    },
  },
  layers: [
    { id: 'land', type: 'background', paint: { 'background-color': globePalette.land } },
    { id: 'relief', type: 'raster', source: 'relief', paint: {
      'raster-saturation': -1, 'raster-contrast': 0.1,
      'raster-brightness-min': 0.38, 'raster-brightness-max': 0.94,
      'raster-opacity': ['interpolate', ['linear'], ['zoom'], 0, 0.35, 3, 0.45, 7, 0.72],
    } },
    { id: 'land-tint', type: 'background', paint: { 'background-color': globePalette.capri, 'background-opacity': 0.57 } },
    // Every fire layer is inserted BEFORE this opaque mask, including its glow.
    // Use the same detailed geography for oceans, lakes, reservoirs and boundaries.
    { id: 'water-mask', type: 'fill', source: 'geography', 'source-layer': 'water',
      filter: ['!=', ['get', 'brunnel'], 'tunnel'], paint: {
        'fill-color': waterColor, 'fill-opacity': 1, 'fill-antialias': false,
      } },
    { id: 'water-outline', type: 'fill', source: 'geography', 'source-layer': 'water',
      filter: ['!=', ['get', 'brunnel'], 'tunnel'], paint: {
        'fill-color': waterColor, 'fill-outline-color': '#82b1c4',
      } },
    { id: 'waterways', type: 'line', source: 'geography', 'source-layer': 'waterway', minzoom: 8,
      filter: ['!=', ['get', 'brunnel'], 'tunnel'], layout: { 'line-cap': 'round' }, paint: {
        'line-color': globePalette.water,
        'line-width': ['interpolate', ['exponential', 1.3], ['zoom'], 8, 0.6, 14, 2, 17, 5],
      } },
    // Cased outlines remain legible against both blue land and red hotspots.
    { id: 'state-border-halo', type: 'line', source: 'geography', 'source-layer': 'boundary', minzoom: 3,
      filter: ['all', ['>=', ['get', 'admin_level'], 3], ['<=', ['get', 'admin_level'], 4], ['!=', ['get', 'maritime'], 1]], paint: {
        'line-color': globePalette.outlineHalo,
        'line-width': ['interpolate', ['linear'], ['zoom'], 3, 1.8, 10, 2.8],
      } },
    { id: 'state-borders', type: 'line', source: 'geography', 'source-layer': 'boundary', minzoom: 3,
      filter: ['all', ['>=', ['get', 'admin_level'], 3], ['<=', ['get', 'admin_level'], 4], ['!=', ['get', 'maritime'], 1]], paint: {
        'line-color': globePalette.outline, 'line-dasharray': [3, 2],
        'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.65, 10, 1.25],
      } },
    { id: 'country-border-halo', type: 'line', source: 'geography', 'source-layer': 'boundary',
      filter: ['all', ['==', ['get', 'admin_level'], 2], ['!=', ['get', 'maritime'], 1]], paint: {
        'line-color': globePalette.outlineHalo,
        'line-width': ['interpolate', ['linear'], ['zoom'], 0, 1.8, 4, 2.4, 10, 3.6],
      } },
    { id: 'country-borders', type: 'line', source: 'geography', 'source-layer': 'boundary',
      filter: ['all', ['==', ['get', 'admin_level'], 2], ['!=', ['get', 'maritime'], 1], ['!=', ['get', 'disputed'], 1]], paint: {
        'line-color': globePalette.outline,
        'line-width': ['interpolate', ['linear'], ['zoom'], 0, 0.7, 4, 1, 10, 1.8],
      } },
    { id: 'disputed-borders', type: 'line', source: 'geography', 'source-layer': 'boundary',
      filter: ['all', ['==', ['get', 'admin_level'], 2], ['!=', ['get', 'maritime'], 1], ['==', ['get', 'disputed'], 1]], paint: {
        'line-color': globePalette.outline, 'line-dasharray': [3, 2],
        'line-width': ['interpolate', ['linear'], ['zoom'], 0, 0.7, 4, 1, 10, 1.8],
    } },
  ],
};

export function landPattern() {
  const size = 8;
  const data = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const i = (y * size + x) * 4;
    data[i] = 6; data[i + 1] = 64; data[i + 2] = 89;
    data[i + 3] = Math.hypot(x - 3.5, y - 3.5) < 1.15 ? 190 : 0;
  }
  return { width: size, height: size, data };
}

// Fine geographic arcs reinforce the globe's depth without decorative imagery.
export const graticule: GeoJSON.FeatureCollection<GeoJSON.LineString> = {
  type: 'FeatureCollection', features: [
    ...Array.from({ length: 12 }, (_, i) => ({ type: 'Feature' as const, properties: {}, geometry: {
      type: 'LineString' as const,
      coordinates: Array.from({ length: 87 }, (_, j) => [-180 + i * 30, -86 + j * 2]),
    } })),
    ...[-60, -30, 0, 30, 60].map(lat => ({ type: 'Feature' as const, properties: {}, geometry: {
      type: 'LineString' as const,
      coordinates: Array.from({ length: 181 }, (_, j) => [-180 + j * 2, lat]),
    } })),
  ],
};
