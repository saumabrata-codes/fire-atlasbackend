import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Map, { Layer, NavigationControl, Popup, ScaleControl, Source, type MapRef, type MapLayerMouseEvent } from 'react-map-gl/maplibre';
import type { HeatmapLayerSpecification } from 'maplibre-gl';
import type { Hotspot } from '../../../lib/api';
import { globePalette, globeStyle, graticule, landPattern } from './globeStyle';
import './globe.css';

type Bounds = [number, number, number, number];
type Props = {
  features: Hotspot[]; loading: boolean; onLocationSelected: (lon: number, lat: number) => void;
  bounds?: Bounds; mode?: 'hotspots' | 'frp' | 'density'; showPoints?: boolean;
  showBoundary?: boolean; drawing?: 'none' | 'rectangle' | 'polygon';
  onBoundsSelected?: (bounds: Bounds) => void;
};
const glow: NonNullable<HeatmapLayerSpecification['paint']> = {
  'heatmap-weight': 1,
  'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 0, 0.8, 5, 1.3, 12, 1.8],
  'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 0, 15, 4, 22, 10, 32],
  // Screen-space heatmaps can spill beyond the sphere's horizon. At globe
  // scale use surface-aligned glow, then blend into density at closer zooms.
  'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 2.8, 0, 3.2, 0.85],
  'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
    0, 'rgba(242,100,80,0)', 0.12, 'rgba(255,133,106,0.18)',
    0.35, 'rgba(250,105,81,0.48)', 0.65, 'rgba(239,73,57,0.82)', 1, '#d63c34'],
};
const motionDuration = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 750;
const fitGlobeZoom = (engine: MapRef | null) => {
  const canvas = engine?.getCanvas();
  const diameter = canvas ? Math.min(canvas.clientWidth - 60, canvas.clientHeight - 120) : 400;
  return Math.log2(Math.max(180, diameter) * Math.PI / 512);
};

export default function WorldMap({ features, loading, onLocationSelected, bounds, mode = 'hotspots', showPoints = true, showBoundary = true, drawing = 'none', onBoundsSelected }: Props) {
  const map = useRef<MapRef>(null);
  const [loaded, setLoaded] = useState(false);
  const [mapError, setMapError] = useState(false);
  const [mapRevision, setMapRevision] = useState(0);
  const [selected, setSelected] = useState<{ lon: number; lat: number; feature?: Hotspot } | null>(null);
  const [vertices, setVertices] = useState<[number, number][]>([]);
  const initialCenter = useRef<[number, number]>(bounds ? [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2] : [30, 18]);
  const previousBounds = useRef(bounds?.join(','));
  const data = useMemo(() => ({ type: 'FeatureCollection' as const, features: features.filter(f => {
    const [lon, lat] = f.geometry.coordinates;
    return Number.isFinite(lon) && Number.isFinite(lat) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
  }) }), [features]);

  useEffect(() => { setVertices([]); setSelected(null); }, [drawing]);
  useEffect(() => { setSelected(null); }, [features]);
  useEffect(() => {
    const key = bounds?.join(',');
    if (!loaded || key === previousBounds.current) return;
    previousBounds.current = key;
    setSelected(null);
    if (bounds) map.current?.fitBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]], { padding: 75, duration: motionDuration(), maxZoom: 10 });
    else map.current?.flyTo({ center: [30, 18], zoom: fitGlobeZoom(map.current), bearing: 0, pitch: 0, duration: motionDuration() });
  }, [bounds, loaded]);

  const onClick = useCallback((e: MapLayerMouseEvent) => {
    const point: [number, number] = [((e.lngLat.lng + 180) % 360 + 360) % 360 - 180, e.lngLat.lat];
    if (drawing !== 'none') {
      const points = [...vertices, point];
      const first = vertices[0];
      const close = drawing === 'polygon' && vertices.length >= 3 && first && Math.hypot(map.current!.project(first).x - e.point.x, map.current!.project(first).y - e.point.y) < 20;
      if ((drawing === 'rectangle' && points.length === 2) || close) {
        const p = close ? vertices : points;
        const xs = p.map(v => v[0]), ys = p.map(v => v[1]);
        const box: Bounds = [Math.max(-180, Math.min(...xs)), Math.max(-90, Math.min(...ys)), Math.min(180, Math.max(...xs)), Math.min(90, Math.max(...ys))];
        if (box[0] < box[2] && box[1] < box[3]) onBoundsSelected?.(box);
        setVertices([]);
      } else setVertices(points);
      return;
    }
    // The invisible hit targets must not select observations hidden by water.
    const onWater = map.current?.queryRenderedFeatures(e.point, { layers: ['water-mask', 'waterways'] }).length;
    const feature = onWater ? undefined : e.features?.find(candidate => {
      const location = (candidate.geometry as GeoJSON.Point).coordinates as [number, number];
      return !map.current?.queryRenderedFeatures(map.current.project(location), { layers: ['water-mask', 'waterways'] }).length;
    }) as unknown as Hotspot | undefined;
    setSelected({ lon: feature?.geometry.coordinates[0] ?? point[0], lat: feature?.geometry.coordinates[1] ?? point[1], feature });
  }, [drawing, vertices, onBoundsSelected]);

  const polygon = bounds ? { type: 'Feature' as const, properties: {}, geometry: { type: 'Polygon' as const, coordinates: [[[bounds[0], bounds[1]], [bounds[2], bounds[1]], [bounds[2], bounds[3]], [bounds[0], bounds[3]], [bounds[0], bounds[1]]]] } } : null;
  return <div className="map-frame globe-frame">
    <Map key={mapRevision} ref={map} initialViewState={{ longitude: initialCenter.current[0], latitude: initialCenter.current[1], zoom: 1.3 }}
      minZoom={-0.5} maxZoom={17} maxPitch={60} mapStyle={globeStyle} canvasContextAttributes={{ antialias: true }}
      onLoad={() => {
        const engine = map.current?.getMap();
        if (engine && !engine.hasImage('land-dots')) engine.addImage('land-dots', landPattern(), { pixelRatio: 2 });
        if (engine && !engine.getLayer('land-texture')) engine.addLayer({ id: 'land-texture', type: 'background', paint: { 'background-pattern': 'land-dots', 'background-opacity': ['interpolate', ['linear'], ['zoom'], 0, 0.65, 4, 0.3, 7, 0.08] } }, 'land-tint');
        engine?.setZoom(fitGlobeZoom(map.current));
        setLoaded(true);
      }}
      onError={event => { console.warn('Globe rendering:', event.error.message); queueMicrotask(() => setMapError(true)); }} onClick={onClick}
      interactiveLayerIds={showPoints ? ['hotspot-hit'] : []} cursor={drawing === 'none' ? 'grab' : 'crosshair'}
      attributionControl={{ compact: true }}>
      <NavigationControl position="top-right" showCompass={false}/>
      <ScaleControl position="bottom-left" unit="metric"/>
      <Source id="graticule" type="geojson" data={graticule}><Layer id="graticule-lines" beforeId="state-border-halo" type="line" paint={{ 'line-color': '#bedce7', 'line-width': 0.6, 'line-opacity': ['interpolate', ['linear'], ['zoom'], 0, 0.2, 5, 0.05] }}/></Source>
      <Source id="fires" type="geojson" data={data}>
        {showPoints && loaded && <>
          <Layer key="fire-surface-glow" id="fire-surface-glow" source="fires" beforeId="water-mask" type="circle" paint={{
            'circle-pitch-alignment': 'map', 'circle-pitch-scale': 'map',
            'circle-radius': mode === 'density' ? 26 : ['interpolate', ['linear'], ['zoom'], 0, 12, 3, 18],
            'circle-color': globePalette.fire,
            'circle-opacity': ['interpolate', ['linear'], ['zoom'], 2.8,
              mode === 'frp' ? ['interpolate', ['linear'], ['coalesce', ['get', 'frp'], 0], 0, 0.07, 100, 0.22, 1000, 0.5] : 0.22,
              3.2, 0], 'circle-blur': 0.85,
          }}/>
          <Layer key="fire-glow" id="fire-glow" source="fires" beforeId="water-mask" type="heatmap" paint={{ ...glow,
            'heatmap-weight': mode === 'frp' ? ['interpolate', ['linear'], ['coalesce', ['get', 'frp'], 0], 0, 0.2, 100, 1, 1000, 3] : 1,
            'heatmap-radius': mode === 'density' ? 38 : glow['heatmap-radius'],
          }}/>
          <Layer key="fire-corona" id="fire-corona" source="fires" beforeId="water-mask" type="circle" paint={{ 'circle-pitch-alignment': 'map', 'circle-pitch-scale': 'map', 'circle-radius': ['interpolate', ['linear'], ['zoom'], 0, 5, 6, 8, 12, 12], 'circle-color': globePalette.fire, 'circle-opacity': mode === 'density' ? 0 : 0.42, 'circle-blur': 0.75 }}/>
          <Layer key="fire-core" id="fire-core" source="fires" beforeId="water-mask" type="circle" paint={{ 'circle-pitch-alignment': 'map', 'circle-pitch-scale': 'map', 'circle-radius': ['interpolate', ['linear'], ['zoom'], 0, 1.7, 5, 2.5, 12, 4], 'circle-color': globePalette.fireCore, 'circle-opacity': mode === 'density' ? 0 : 0.9, 'circle-blur': 0.35 }}/>
        </>}
      </Source>
      {/* Above the opaque mask for reliable hit testing; onClick rejects water. */}
      {showPoints && loaded && <Layer id="hotspot-hit" source="fires" type="circle" paint={{ 'circle-radius': 13, 'circle-opacity': 0 }}/>}
      {polygon && showBoundary && <Source id="area" type="geojson" data={polygon}><Layer id="area-fill" type="fill" paint={{ 'fill-color': globePalette.capri, 'fill-opacity': 0.025 }}/><Layer id="area-border-halo" type="line" paint={{ 'line-color': globePalette.outlineHalo, 'line-width': 3 }}/><Layer id="area-border" type="line" paint={{ 'line-color': globePalette.outline, 'line-width': 1.4, 'line-dasharray': [3, 3] }}/></Source>}
      {vertices.length > 0 && <Source id="drawing" type="geojson" data={{ type: 'FeatureCollection', features: [
        ...vertices.map(coordinates => ({ type: 'Feature' as const, properties: {}, geometry: { type: 'Point' as const, coordinates } })),
        ...(vertices.length > 1 ? [{ type: 'Feature' as const, properties: {}, geometry: { type: 'LineString' as const, coordinates: vertices } }] : []),
      ] }}><Layer id="draw-line" type="line" paint={{ 'line-color': '#374c40', 'line-width': 2 }}/><Layer id="draw-point" type="circle" filter={['==', '$type', 'Point']} paint={{ 'circle-color': '#374c40', 'circle-radius': 5, 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' }}/></Source>}
      {selected && <Popup longitude={selected.lon} latitude={selected.lat} anchor="bottom" closeOnClick={false} onClose={() => setSelected(null)}><div className="fire-popup"><strong>{selected.feature ? 'Fire observation' : 'Explore this location'}</strong><span>{selected.lat.toFixed(4)}° latitude · {selected.lon.toFixed(4)}° longitude</span>{selected.feature ? <><span>{new Date(selected.feature.properties.acq_datetime).toUTCString()}</span><span>Fire radiative power: {selected.feature.properties.frp ?? '—'} MW</span><span>Confidence: {selected.feature.properties.confidence ?? 'Not provided'}</span></> : <button className="globe-region-button" onClick={() => { onLocationSelected(selected.lon, selected.lat); setSelected(null); }}>Study this area</button>}</div></Popup>}
    </Map>
    <div className="globe-actions"><button onClick={() => map.current?.flyTo({ center: bounds ? [(bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2] : [30, 18], zoom: fitGlobeZoom(map.current), bearing: 0, pitch: 0, duration: motionDuration() })}>Reset globe</button>{bounds && <button onClick={() => map.current?.fitBounds([[bounds[0], bounds[1]], [bounds[2], bounds[3]]], { padding: 65, maxZoom: 10, duration: motionDuration() })}>Focus area</button>}</div>
    <div className="globe-instructions">Drag to rotate <span>·</span> Scroll or pinch to zoom</div>
    {loading && <div className="map-busy" role="status">Loading observations…</div>}
    {mapError && <div className="globe-network-note" role="status">Some map detail could not load. Check your connection.<button onClick={() => { setMapError(false); setLoaded(false); setMapRevision(value => value + 1); }}>Retry</button></div>}
    {drawing !== 'none' && <div className="drawing-hint">{drawing === 'rectangle' ? vertices.length ? 'Choose the opposite corner' : 'Choose the first corner' : vertices.length + ' vertices · Select the first point to finish'}</div>}
  </div>;
}
