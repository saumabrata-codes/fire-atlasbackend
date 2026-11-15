import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { getActivitySeries, getAnomalySummary, getHotspots, getReportUrl, type ActivityBucket, type Hotspot, type ObservationFilters } from '../lib/api';
import WorldMap from '../features/explore-map/components/WorldMap';
import AtlasChart from './AtlasChart';

type View = 'overview' | 'map' | 'calendar' | 'activity' | 'anomalies' | 'reports';
type LoadState = 'loading' | 'ready' | 'error';
type Resource<T> = { status: LoadState; data: T; sample?: boolean };
type Anomaly = Awaited<ReturnType<typeof getAnomalySummary>>;
const tabs: { id: View; label: string; subtitle: string }[] = [
  { id: 'overview', label: 'Overview', subtitle: 'Fire activity across regions and time.' },
  { id: 'map', label: 'Explore Map', subtitle: 'Rotate the globe, select a region, and explore fire activity.' },
  { id: 'calendar', label: 'Fire Calendar', subtitle: 'Daily and monthly patterns in the observation record.' },
  { id: 'activity', label: 'Activity Analysis', subtitle: 'Understand detection patterns and fire radiative power.' },
  { id: 'anomalies', label: 'Anomaly Insights', subtitle: 'Assess recent activity against the available history.' },
  { id: 'reports', label: 'Reports', subtitle: 'Download observations and summaries for your selection.' },
];
const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const fmt = (value: number | null | undefined) => value == null || !Number.isFinite(value) ? '—' : value.toLocaleString(undefined, { maximumFractionDigits: 1 });
const compact = (value: number) => Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(value);
const dateLabel = (value?: string, fallback = '—') => value
  ? new Date(value.slice(0, 10) + 'T00:00:00Z').toLocaleDateString('en', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
  : fallback;
const stateText: Record<LoadState, string> = {
  loading: 'Loading stored observations…',
  ready: 'No stored observations for this selection. Coverage is unknown.',
  error: 'This data could not be loaded. Use Retry to try again.',
};

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, string> = {
    overview: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
    map: 'M3 5 9 3l6 3 6-3v16l-6 3-6-3-6 2zM9 3v16m6-13v16',
    calendar: 'M4 5h16v16H4zM8 2v6m8-6v6M4 10h16M8 14h1m3 0h1m3 0h1m-9 4h1m3 0h1',
    activity: 'M4 20V10m8 10V4m8 16v-7M2 20h20',
    anomalies: 'M3 17 8 12l4 3 8-10M14 5h6v6',
    reports: 'M12 3v12m-5-5 5 5 5-5M4 15v6h16v-6',
    pin: 'M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0ZM10 10a2 2 0 1 0 4 0 2 2 0 1 0-4 0',
    layers: 'm3 7 9-5 9 5-9 5zM3 12l9 5 9-5M3 17l9 5 9-5',
    refresh: 'M20 8a8 8 0 0 0-14-3L3 8m0-6v6h6m-5 8a8 8 0 0 0 14 3l3-3m0 6v-6h-6',
    info: 'M12 11v6m0-10v.1M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
    rectangle: 'M3 4h18v16H3z', polygon: 'm3 8 9-5 8 6-3 12H6z',
    target: 'M12 2v4m0 12v4M2 12h4m12 0h4M19 12a7 7 0 1 1-14 0 7 7 0 0 1 14 0',
    bolt: 'm14 2-9 12h7l-2 8 9-12h-7z', close: 'm5 5 14 14M5 19 19 5',
    chevron: 'm9 5 7 7-7 7', arrow: 'M4 12h16m-6-6 6 6-6 6',
    globe: 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0M2 12h20M12 2c6 6 6 14 0 20-6-6-6-14 0-20',
    clock: 'M12 7v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
    document: 'M14 2H5v20h14V7zM14 2v5h5M8 12h8m-8 4h8',
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name] || paths.activity}/></svg>;
}

function Panel({ title, eyebrow, action, children, className = '' }: { title: string; eyebrow?: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={'atlas-panel ' + className}>
    <div className="panel-heading"><div>{eyebrow && <span className="eyebrow">{eyebrow}</span>}<h2>{title}</h2></div>{action}</div>
    {children}
  </section>;
}
function Metric({ label, value, detail, icon, accent = false }: { label: string; value: string; detail: string; icon: string; accent?: boolean }) {
  return <div className={'atlas-metric' + (accent ? ' metric-accent' : '')}>
    <div className="metric-label"><span>{label}</span><Icon name={icon} size={18}/></div>
    <strong>{value}</strong><small>{detail}</small>
  </div>;
}
function Empty({ status = 'ready', children }: { status?: LoadState; children?: ReactNode }) {
  return <div className="atlas-empty" role={status === 'loading' ? 'status' : undefined}><Icon name={status === 'loading' ? 'clock' : 'info'} size={24}/><p>{children || stateText[status]}</p></div>;
}

// A neutral cell means unknown coverage; an explicit zero has its own appearance.
function heat(value: number | undefined, max: number) {
  if (value == null) return { background: '#f1f0ec', color: '#7d8079' };
  if (value === 0) return { background: '#ffffff', color: '#575c55' };
  const colors = ['#f5e9e5', '#ead2ca', '#dcb4a9', '#c58d80', '#ad665b'];
  const level = Math.min(4, Math.floor(value / Math.max(1, max) * 4));
  return { background: colors[level], color: level > 2 ? '#ffffff' : '#653d36' };
}
function HeatLegend() {
  return <div className="heatmap-caption"><span><i className="unknown-cell"/>Unknown</span><span><i className="zero-cell"/>0</span><span>Low <i className="heat-gradient"/> High</span></div>;
}
function MonthCalendar({ rows, initial, status }: { rows: ActivityBucket[]; initial: string; status: LoadState }) {
  const [month, setMonth] = useState(initial.slice(0, 7));
  useEffect(() => setMonth(initial.slice(0, 7)), [initial]);
  const date = new Date(month + '-01T00:00:00Z');
  const count = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate();
  const byDate = new Map(rows.map(row => [row.period_start.slice(0, 10), row.total]));
  const max = Math.max(1, ...rows.filter(row => row.period_start.startsWith(month)).map(row => row.total));
  const move = (amount: number) => setMonth(new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + amount, 1)).toISOString().slice(0, 7));
  return <Panel title={months[date.getUTCMonth()] + ' ' + date.getUTCFullYear()} eyebrow="Daily calendar" action={<div className="calendar-arrows">
    <button className="icon-button previous" aria-label="Previous month" onClick={() => move(-1)}><Icon name="chevron" size={16}/></button>
    <button className="icon-button" aria-label="Next month" onClick={() => move(1)}><Icon name="chevron" size={16}/></button>
  </div>}>
    {status !== 'ready' ? <Empty status={status}/> : <>
      <div className="month-grid">
        {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((day, index) => <b key={index}>{day}</b>)}
        {Array.from({ length: date.getUTCDay() }, (_, index) => <span key={'blank-' + index}/>)}
        {Array.from({ length: count }, (_, index) => {
          const key = month + '-' + String(index + 1).padStart(2, '0');
          const value = byDate.get(key);
          const label = dateLabel(key) + ': ' + (value == null ? 'Unknown coverage' : fmt(value) + ' detections');
          return <button key={key} type="button" title={label} aria-label={label} style={heat(value, max)}>{index + 1}</button>;
        })}
      </div><HeatLegend/><p className="panel-note">Daily totals within your applied date range. Shading is relative to this month.</p>
    </>}
  </Panel>;
}
function downloadCsv(name: string, rows: (string | number)[][]) {
  const csv = rows.map(row => row.map(value => '"' + String(value).replace(/"/g, '""') + '"').join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
  const anchor = document.createElement('a');
  anchor.href = url; anchor.download = name; anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function AboutDialog({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    return () => { previous?.focus(); };
  }, []);
  return <dialog ref={ref} className="about-dialog" aria-labelledby="about-title" onCancel={onClose} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <button className="icon-button dialog-close" aria-label="Close about the data" autoFocus onClick={onClose}><Icon name="close"/></button>
    <span className="eyebrow">Reading the record</span><h2 id="about-title">About the data</h2>
    <p>Fire Atlas explores stored NASA FIRMS active fire observations. All available observations are included in each selection.</p>
    <p>A detection is a satellite observation, not a unique fire. Overlapping observations are not deduplicated or claimed to be measurement-equivalent.</p>
    <p>Missing periods mean unknown coverage, never zero fire activity. Days with records describe the available record, not complete satellite coverage of a region.</p>
    <p>FRP is fire radiative power in megawatts. The mean is weighted by the number of observations with an FRP value; it does not measure the size of a fire.</p>
    <p>Map records may be limited. Charts and summary metrics use stored aggregate totals. The monthly anomaly screen is preliminary, not a formal historical anomaly score.</p>
  </dialog>;
}

export default function App() {
  const [view, setView] = useState<View>('overview');
  useEffect(() => { window.scrollTo(0, 0); }, [view]);
  const [defaults] = useState(() => ({
    start: new Date(Date.now() - 183 * 86400000).toISOString().slice(0, 10),
    end: new Date(Date.now() - 86400000).toISOString().slice(0, 10),
  }));
  const [area, setArea] = useState('india');
  const [areaName, setAreaName] = useState('India');
  const [start, setStart] = useState(defaults.start);
  const [end, setEnd] = useState(defaults.end);
  const [bboxText, setBboxText] = useState('');
  const [filters, setFilters] = useState<ObservationFilters>({ ...defaults, bbox: [68, 8, 97, 37] });
  const [daily, setDaily] = useState<Resource<ActivityBucket[]>>({ status: 'loading', data: [] });
  const [monthly, setMonthly] = useState<Resource<ActivityBucket[]>>({ status: 'loading', data: [] });
  const [hotspots, setHotspots] = useState<Resource<Hotspot[]>>({ status: 'loading', data: [] });
  const [anomaly, setAnomaly] = useState<Resource<Anomaly | null>>({ status: 'loading', data: null });
  const [revision, setRevision] = useState(0);
  const [validation, setValidation] = useState('');
  const [coordinates, setCoordinates] = useState(false);
  const [about, setAbout] = useState(false);
  const [layer, setLayer] = useState<'hotspots' | 'frp' | 'density'>('hotspots');
  const [showPoints, setShowPoints] = useState(true);
  const [showBoundary, setShowBoundary] = useState(true);
  const [drawing, setDrawing] = useState<'none' | 'rectangle' | 'polygon'>('none');
  const [period, setPeriod] = useState<'day' | 'month'>('day');

  useEffect(() => {
    let current = true;
    setDaily({ status: 'loading', data: [] }); setMonthly({ status: 'loading', data: [] });
    setHotspots({ status: 'loading', data: [] }); setAnomaly({ status: 'loading', data: null });
    const loadActivity = (bucket: 'day' | 'month', setter: typeof setDaily) => {
      getActivitySeries(filters, 'ALL', bucket).then(result => {
        if (current) setter({ status: 'ready', sample: result.sample_mode, data: [...result.series].sort((a, b) => a.period_start.localeCompare(b.period_start)) });
      }).catch(() => { if (current) setter({ status: 'error', data: [] }); });
    };
    loadActivity('day', setDaily); loadActivity('month', setMonthly);
    getHotspots('ALL', filters).then(result => {
      if (current) setHotspots({ status: 'ready', sample: result.sample_mode, data: result.features });
    }).catch(() => { if (current) setHotspots({ status: 'error', data: [] }); });
    getAnomalySummary(filters, 'ALL').then(result => {
      const sample = (result as Anomaly & { sample_mode?: boolean }).sample_mode;
      if (current) setAnomaly({ status: 'ready', sample, data: result });
    }).catch(() => { if (current) setAnomaly({ status: 'error', data: null }); });
    return () => { current = false; };
  }, [filters, revision]);

  const states = [daily.status, monthly.status, hotspots.status, anomaly.status];
  const loading = states.includes('loading');
  const failed = states.includes('error');
  const sample = [daily, monthly, hotspots, anomaly].some(resource => resource.sample);
  const activeTab = tabs.find(tab => tab.id === view)!;
  const totals = useMemo(() => daily.data.reduce((sum, row) => {
    sum.count += row.total;
    if (row.frp_sum_mw != null && Number.isFinite(row.frp_sum_mw) && (row.frp_observation_count || 0) > 0) {
      sum.frp += row.frp_sum_mw;
      sum.frpCount += row.frp_observation_count!;
    }
    return sum;
  }, { count: 0, frp: 0, frpCount: 0 }), [daily.data]);
  const hasDaily = daily.status === 'ready' && daily.data.length > 0;
  const hasMonthly = monthly.status === 'ready' && monthly.data.length > 0;
  const total = hasDaily ? totals.count : null;
  const mean = totals.frpCount ? totals.frp / totals.frpCount : null;
  const storedDays = new Set(daily.data.filter(row => row.covered_days == null || row.covered_days > 0).map(row => row.period_start.slice(0, 10))).size;
  const daysInRange = filters.start && filters.end ? Math.round((Date.parse(filters.end) - Date.parse(filters.start)) / 86400000) + 1 : null;
  const latest = daily.data[daily.data.length - 1]?.period_start;
  const currentDate = filters.end || latest?.slice(0, 10) || defaults.end;
  const peak = monthly.data.length ? monthly.data.reduce((a, b) => a.total >= b.total ? a : b) : null;
  const busiest = daily.data.length ? daily.data.reduce((a, b) => a.total >= b.total ? a : b) : null;
  const sortedCounts = monthly.data.map(row => row.total).sort((a, b) => a - b);
  const median = sortedCounts.length ? (sortedCounts[Math.floor((sortedCounts.length - 1) / 2)] + sortedCounts[Math.floor(sortedCounts.length / 2)]) / 2 : null;
  const years = Array.from(new Set(monthly.data.map(row => row.period_start.slice(0, 4)))).sort().reverse();
  const seasonal = months.map((month, index) => {
    const rows = monthly.data.filter(row => Number(row.period_start.slice(5, 7)) === index + 1);
    return { period_start: month, total: rows.length ? rows.reduce((sum, row) => sum + row.total, 0) / rows.length : NaN };
  });
  const frpFeatures = hotspots.data.filter(feature => feature.properties.frp != null && Number.isFinite(feature.properties.frp) && feature.properties.frp >= 0);
  const rangeLabel = dateLabel(filters.start, 'Earliest stored date') + ' — ' + dateLabel(filters.end, 'Latest stored date');
  const boundsLabel = filters.bbox ? filters.bbox.map(value => value.toFixed(2)).join(', ') : 'All available regions';
  const value = (number: number | null, status = daily.status) => status === 'loading' ? '…' : status === 'ready' ? fmt(number) : '—';

  const apply = () => {
    if (start && end && start > end) { setValidation('Start date must be on or before end date.'); return; }
    let bbox: ObservationFilters['bbox'];
    if (area === 'india') bbox = [68, 8, 97, 37];
    else if (area === 'amazon') bbox = [-74, -18, -44, 6];
    else if (area === 'custom') {
      const parts = bboxText.split(',');
      const numbers = parts.map(part => Number(part.trim()));
      if (numbers.length !== 4 || parts.some(part => !part.trim()) || numbers.some(number => !Number.isFinite(number)) ||
        numbers[0] < -180 || numbers[2] > 180 || numbers[1] < -90 || numbers[3] > 90 || numbers[0] >= numbers[2] || numbers[1] >= numbers[3]) {
        setValidation('Enter west, south, east, north with valid longitude and latitude bounds.'); setCoordinates(true); return;
      }
      bbox = numbers as ObservationFilters['bbox'];
    }
    setValidation(''); setCoordinates(false); setDrawing('none');
    setAreaName(area === 'india' ? 'India' : area === 'amazon' ? 'Amazon Basin' : area === 'custom' ? 'Custom study area' : 'Global');
    setFilters({ start: start || undefined, end: end || undefined, bbox }); setRevision(number => number + 1);
  };
  const pickBounds = (bbox: [number, number, number, number]) => {
    setArea('custom'); setAreaName('Selected study area'); setBboxText(bbox.map(number => number.toFixed(5)).join(', '));
    setFilters(previous => ({ ...previous, bbox })); setDrawing('none'); setValidation('');
  };
  const pick = (lon: number, lat: number) => {
    const x = ((lon + 180) % 360 + 360) % 360 - 180;
    pickBounds([Math.max(-180, x - .125), Math.max(-90, lat - .125), Math.min(180, x + .125), Math.min(90, lat + .125)]);
  };
  const resetArea = () => {
    setArea('global'); setAreaName('Global'); setDrawing('none'); setCoordinates(false); setValidation('');
    setFilters(previous => ({ ...previous, bbox: undefined }));
  };

  const metrics = <div className="atlas-metrics">
    <Metric icon="activity" label="Total detections" value={value(total)} detail="Stored aggregate observations" accent/>
    <Metric icon="bolt" label="Mean radiative power" value={value(mean) + (hasDaily && mean != null ? ' MW' : '')} detail={hasDaily ? fmt(totals.frpCount) + ' observations with FRP' : 'Weighted by available observations'}/>
    <Metric icon="calendar" label="Days with records" value={value(hasDaily ? storedDays : null)} detail={daysInRange ? 'Within ' + fmt(daysInRange) + ' selected days' : 'Within the selected period'}/>
    <Metric icon="clock" label="Latest stored day" value={daily.status === 'loading' ? '…' : dateLabel(latest)} detail="In this region and date range"/>
  </div>;
  const timelineData = period === 'day' ? daily : monthly;
  const timeline = <Panel title="Activity over time" eyebrow="Detection timeline" action={<div className="segmented" aria-label="Timeline interval">
    {(['day', 'month'] as const).map(option => <button key={option} aria-pressed={period === option} className={period === option ? 'active' : ''} onClick={() => setPeriod(option)}>{option === 'day' ? 'Daily' : 'Monthly'}</button>)}
  </div>}>
    {timelineData.status === 'ready' && timelineData.data.length ? <AtlasChart type="bar" rows={timelineData.data} period={period}/> : <Empty status={timelineData.status}/>}
    <div className="chart-caption"><span><i className="activity-dot"/>Total detections</span><span>Missing periods are unknown</span></div>
  </Panel>;
  const map = <section className={'atlas-map ' + (view === 'map' ? 'expanded-map' : '')} aria-label="Interactive fire activity globe">
    <WorldMap features={hotspots.data} loading={hotspots.status === 'loading'} onLocationSelected={pick} bounds={filters.bbox} mode={layer} showPoints={showPoints} showBoundary={showBoundary} drawing={drawing} onBoundsSelected={pickBounds}/>
    <div className="map-segment segmented" aria-label="Map layer">{(['hotspots', 'frp', 'density'] as const).map(option => <button key={option} aria-pressed={layer === option} className={layer === option ? 'active' : ''} onClick={() => setLayer(option)}>{option === 'hotspots' ? 'Hotspots' : option === 'frp' ? 'FRP' : 'Density'}</button>)}</div>
    <div className="map-key">
      <span><i className="activity-dot"/>{showPoints ? layer === 'frp' ? 'Radiative power' : layer === 'density' ? 'Activity density' : 'Fire detections' : 'Observations hidden'}</span>
      {showBoundary && filters.bbox && <span><i className="boundary-key"/>Selected area</span>}
      <small>{hotspots.status === 'ready' ? fmt(hotspots.data.length) + ' loaded records · map may be limited' : hotspots.status === 'loading' ? 'Loading map records…' : 'Map observations unavailable'}</small>
    </div>
    {hotspots.status !== 'loading' && (hotspots.status !== 'ready' || !hotspots.data.length) && <div className="map-data-note" role="status">{hotspots.status === 'ready' ? 'No stored map observations in this selection.' : stateText[hotspots.status]}</div>}
  </section>;
  const anomalyTitle = anomaly.status === 'loading' ? 'Checking available history' : anomaly.status !== 'ready' ? 'Assessment unavailable' : anomaly.data?.available ? 'Monthly screen available' : 'More history needed';
  const anomalyCopy = anomaly.status === 'ready' ? anomaly.data?.result || anomaly.data?.reason || 'No assessment was returned.' : stateText[anomaly.status];
  const summaryRail = <aside className="overview-rail">
    <Panel title={areaName} eyebrow="Your study area" className="selection-summary">
      <p className="selection-period">{rangeLabel}</p>
      <dl className="summary-list">
        <div><dt>Geographic bounds</dt><dd>{boundsLabel}</dd></div>
        <div><dt>Record availability</dt><dd>{hasDaily ? fmt(storedDays) + (storedDays === 1 ? ' day with records' : ' days with records') : daily.status === 'loading' ? 'Loading…' : 'No record coverage to report'}</dd></div>
        <div><dt>Highest daily count</dt><dd>{busiest ? fmt(busiest.total) + ' · ' + dateLabel(busiest.period_start) : '—'}</dd></div>
      </dl>
      <button className="text-button" onClick={() => setView('map')}>Explore this region<Icon name="arrow" size={17}/></button>
    </Panel>
    <Panel title={anomalyTitle} eyebrow="Historical assessment" className="insight-card">
      <p>{anomalyCopy}</p><small>Preliminary monthly screen. A validated baseline is required for formal anomaly scores.</small>
      <button className="text-button" onClick={() => setView('anomalies')}>View insights<Icon name="arrow" size={17}/></button>
    </Panel>
  </aside>;
  const exportPrefix = (sample ? 'fireatlas-demo-' : 'fireatlas-') + areaName.toLowerCase().replace(/\s+/g, '-') + '-' + (filters.start || 'all') + '-' + (filters.end || 'latest');
  const reportRows = [
    { title: 'Observation records', description: 'Records for the selected region and dates. Up to 10,000 rows.', format: 'CSV', icon: 'layers', enabled: hotspots.status === 'ready' && hotspots.data.length > 0, action: () => window.open(getReportUrl('csv', 'ALL', filters), '_blank', 'noopener,noreferrer') },
    { title: 'Yearly activity summary', description: 'Total detections by year within the applied date range.', format: 'CSV', icon: 'calendar', enabled: hasMonthly, action: () => {
      const yearly = new Map<string, number>();
      monthly.data.forEach(row => { const year = row.period_start.slice(0, 4); yearly.set(year, (yearly.get(year) || 0) + row.total); });
      downloadCsv(exportPrefix + '-yearly.csv', [['Year', 'Total detections'], ...Array.from(yearly)]);
    } },
    { title: 'Monthly activity statistics', description: 'Total detections, mean FRP and available observation counts.', format: 'CSV', icon: 'activity', enabled: hasMonthly, action: () => downloadCsv(exportPrefix + '-monthly.csv', [
      ['Month', 'Total detections', 'Mean FRP (MW)', 'Observations with FRP', 'Days with records'],
      ...monthly.data.map(row => [row.period_start.slice(0, 7), row.total, row.frp_mean_mw ?? '', row.frp_observation_count ?? '', row.covered_days ?? '']),
    ]) },
    { title: 'Selection summary', description: 'A clean summary of aggregate totals. Print or save as PDF from the print dialog.', format: 'PDF', icon: 'document', enabled: hasDaily, action: () => window.print() },
  ];

  return <div className="atlas-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="atlas-sidebar">
      <button className="atlas-brand" onClick={() => setView('overview')} aria-label="Fire Atlas overview"><span>FIRE<span className="brand-slash"> / </span>ATLAS</span><small>EARTH OBSERVATION ATLAS</small></button>
      <div className="nav-label">Workspace</div>
      <nav aria-label="Main navigation">{tabs.map(tab => <button key={tab.id} className={view === tab.id ? 'selected' : ''} onClick={() => { setView(tab.id); setDrawing('none'); }} aria-current={view === tab.id ? 'page' : undefined}><Icon name={tab.id}/><span>{tab.label}</span>{view === tab.id && <span className="nav-indicator"/>}</button>)}</nav>
      <div className="sidebar-bottom"><span className="eyebrow">Earth observation</span><p>Regional patterns.<br/>Global context.</p><div className="sidebar-source"><Icon name="globe" size={16}/><span>NASA FIRMS observations</span></div></div>
    </aside>
    <main id="main-content" className="atlas-main" tabIndex={-1}>
      <header className="atlas-header"><div><div className="page-kicker">Fire Atlas <span>/</span> {activeTab.label}</div><h1>{activeTab.label}</h1><p>{activeTab.subtitle}</p></div><button className="subtle-button about-button" onClick={() => setAbout(true)}><Icon name="info" size={17}/>About the data</button></header>
      <form className="atlas-controls" onSubmit={event => { event.preventDefault(); apply(); }}>
        <div className="area-filter"><Icon name="pin" size={19}/><label htmlFor="area">Area of interest<select id="area" value={area} onChange={event => { setArea(event.target.value); setCoordinates(event.target.value === 'custom'); }}><option value="india">India</option><option value="global">Global</option><option value="amazon">Amazon Basin</option><option value="custom">Custom study area</option></select></label></div>
        <fieldset className="dates-filter"><legend>Date range</legend><div className="date-inputs"><Icon name="calendar" size={18}/><input aria-label="Start date" type="date" value={start} onChange={event => setStart(event.target.value)}/><span>—</span><input aria-label="End date" type="date" value={end} onChange={event => setEnd(event.target.value)}/></div></fieldset>
        <button className="primary-button update-button" type="submit"><Icon name="refresh" size={17}/>Update view</button>
      </form>
      {coordinates && <div className="coordinate-entry"><label htmlFor="coordinates">Bounds · west, south, east, north<input id="coordinates" value={bboxText} onChange={event => { setBboxText(event.target.value); setArea('custom'); }} placeholder="68, 8, 97, 37"/></label><button className="primary-button" onClick={apply}>Apply area</button><button className="subtle-button" onClick={() => setCoordinates(false)}>Close</button></div>}
      {validation && <div className="atlas-notice is-error" role="alert"><Icon name="info" size={18}/>{validation}</div>}
      {failed && <div className="atlas-notice is-error" role="alert"><Icon name="info" size={18}/><span>Some data could not be loaded. Available panels show the records that were returned.</span><button className="text-button" onClick={() => setRevision(number => number + 1)}>Retry<Icon name="refresh" size={15}/></button></div>}
      {sample && <div className="atlas-notice" role="status"><Icon name="info" size={18}/>Demonstration data is included in this preview. These sample observations do not represent current fire conditions.</div>}
      <div className="selection-context"><span><i className="context-dot"/>{areaName}<span className="context-divider">/</span>{rangeLabel}</span><span role="status">{loading ? 'Updating observations…' : failed ? 'Partially available' : sample ? 'Demonstration data' : 'Stored observations'}</span></div>

      {view === 'overview' && <><div className="overview-top">{map}{summaryRail}</div>{metrics}<div className="overview-bottom">{timeline}<MonthCalendar rows={daily.data} initial={currentDate} status={daily.status}/></div></>}

      {view === 'map' && <div className="explore-layout">{map}<aside className="map-tools">
        <Panel title="Shape your study area" eyebrow="Map tools">
          <button className={'tool ' + (drawing === 'rectangle' ? 'active' : '')} aria-pressed={drawing === 'rectangle'} onClick={() => setDrawing(drawing === 'rectangle' ? 'none' : 'rectangle')}><Icon name="rectangle"/>Draw a rectangle</button>
          <button className={'tool ' + (drawing === 'polygon' ? 'active' : '')} aria-pressed={drawing === 'polygon'} onClick={() => setDrawing(drawing === 'polygon' ? 'none' : 'polygon')}><Icon name="polygon"/>Draw a polygon</button>
          <button className="tool" onClick={() => { setCoordinates(true); setArea('custom'); }}><Icon name="target"/>Enter coordinates</button>
          <button className="tool" onClick={resetArea}><Icon name="globe"/>Use global selection</button>
          <p className="panel-note">{drawing === 'rectangle' ? 'Click two opposite corners to select an area.' : drawing === 'polygon' ? 'Click vertices, then the first vertex to finish. Analysis uses the polygon’s bounding rectangle.' : 'Select a location, then choose “Study this area” to explore a 0.25° region.'}</p>
        </Panel>
        <Panel title="Visible layers" eyebrow="Map appearance">
          <label className="layer-check"><input type="checkbox" checked={showPoints} onChange={event => setShowPoints(event.target.checked)}/>Fire observations</label>
          <label className="layer-check"><input type="checkbox" checked={layer === 'density'} onChange={event => setLayer(event.target.checked ? 'density' : 'hotspots')}/>Activity density</label>
          <label className="layer-check"><input type="checkbox" checked={showBoundary} onChange={event => setShowBoundary(event.target.checked)}/>Selected area boundary</label>
        </Panel>
        <div className="inset-note"><span className="eyebrow">{areaName}</span><p>{boundsLabel}</p><small>Map records may be limited. Summary metrics and charts use aggregate totals.</small></div>
      </aside></div>}

      {view === 'calendar' && <>
        <div className="atlas-metrics">
          <Metric icon="calendar" label="Peak month" value={peak ? months[Number(peak.period_start.slice(5, 7)) - 1] + ' ' + peak.period_start.slice(0, 4) : value(null, monthly.status)} detail={peak ? fmt(peak.total) + ' detections' : 'Within the available record'} accent/>
          <Metric icon="activity" label="Monthly median" value={value(median, monthly.status)} detail="Across stored monthly totals"/>
          <Metric icon="layers" label="Months with records" value={value(hasMonthly ? monthly.data.length : null, monthly.status)} detail="Missing months remain unknown"/>
          <Metric icon="clock" label="Years represented" value={value(hasMonthly ? years.length : null, monthly.status)} detail="Within the selected date range"/>
        </div>
        <Panel title="A year at a glance" eyebrow="Historical monthly activity" action={<span className="panel-meta">Total detections</span>}>
          {hasMonthly ? <><div className="year-heatmap"><table><caption className="sr-only">Monthly detection totals by year. A dash indicates unknown coverage.</caption><thead><tr><th scope="col">Year</th>{months.map(month => <th scope="col" key={month}>{month}</th>)}</tr></thead><tbody>{years.map(year => <tr key={year}><th scope="row">{year}</th>{months.map((month, index) => {
            const row = monthly.data.find(item => item.period_start.slice(0, 7) === year + '-' + String(index + 1).padStart(2, '0'));
            const label = month + ' ' + year + ': ' + (row ? fmt(row.total) + ' detections' : 'Unknown coverage');
            return <td key={month} style={heat(row?.total, peak?.total || 1)} title={label} aria-label={label}>{row ? compact(row.total) : '—'}</td>;
          })}</tr>)}</tbody></table></div><HeatLegend/></> : <Empty status={monthly.status}/>}
          <p className="panel-note">Totals reflect only available records in the applied date range. Partial months and years may be included.</p>
        </Panel>
        <div className="calendar-bottom"><Panel title="The seasonal pattern" eyebrow="Mean monthly activity">{hasMonthly ? <AtlasChart type="line" rows={seasonal}/> : <Empty status={monthly.status}/>}<p className="panel-note">Mean of available monthly totals across selected years. Missing months are excluded; coverage may differ.</p></Panel><MonthCalendar rows={daily.data} initial={currentDate} status={daily.status}/></div>
      </>}

      {view === 'activity' && <>{metrics}<div className="two-charts">{timeline}<Panel title="Radiative power distribution" eyebrow="Loaded map observations">
        {hotspots.status === 'ready' && frpFeatures.length ? <AtlasChart type="distribution" features={frpFeatures}/> : <Empty status={hotspots.status}>{hotspots.status === 'ready' ? 'No valid FRP measurements in the loaded map records.' : undefined}</Empty>}
        <p className="panel-note">{hotspots.status === 'ready' ? fmt(frpFeatures.length) + ' loaded records with valid FRP. ' : ''}Ranges in MW; lower bound inclusive, upper bound exclusive. This subset is not a full-population estimate.</p>
      </Panel></div><Panel title="Understanding the measurements" eyebrow="Context matters"><div className="takeaways">
        <div><Icon name="target"/><h3>Observations, not individual fires</h3><p>A fire can be observed more than once. Counts describe the stored detection record.</p></div>
        <div><Icon name="bolt"/><h3>Energy, expressed in megawatts</h3><p>FRP describes radiative power. It does not measure a fire’s area or burned extent.</p></div>
        <div><Icon name="calendar"/><h3>Coverage shapes the picture</h3><p>Gaps are unknown, not zero. Compare periods with their record availability in mind.</p></div>
      </div></Panel></>}

      {view === 'anomalies' && <>
        <section className="assessment-banner"><span className="assessment-icon"><Icon name="anomalies" size={25}/></span><div><span className="eyebrow">Preliminary assessment</span><h2>{anomalyTitle}</h2><p>Formal historical anomaly scores require a matched, coverage-validated baseline.</p></div><span className="status-badge">{anomaly.status === 'loading' ? 'Loading' : anomaly.data?.available ? 'Screen available' : 'Not scored'}</span></section>
        <div className="two-charts"><Panel title="What the record suggests" eyebrow="Monthly screen"><p className="insight-summary">{anomalyCopy}</p>{anomaly.data?.reason && anomaly.data.reason !== anomalyCopy && <p className="panel-note">{anomaly.data.reason}</p>}<dl className="summary-list"><div><dt>Days reported by assessment</dt><dd>{value(anomaly.data?.covered_days ?? null, anomaly.status)}</dd></div><div><dt>Missing observations</dt><dd>Never treated as zero</dd></div></dl></Panel><Panel title="Stored monthly activity" eyebrow="The supporting record">{hasMonthly ? <AtlasChart type="line" rows={monthly.data} period="month"/> : <Empty status={monthly.status}/>}</Panel></div>
        <Panel title="The limits of this assessment" eyebrow="Interpret with care"><div className="takeaways">
          <div><h3>Consecutive history</h3><p>The elementary screen requires at least six consecutive monthly buckets with stored detections.</p></div>
          <div><h3>Comparable coverage</h3><p>Changes in observation availability can affect counts. A potential spike does not establish an unusual fire event.</p></div>
          <div><h3>No formal score</h3><p>Historical change, z-scores and percentiles are unavailable without a validated baseline.</p></div>
        </div></Panel>
      </>}

      {view === 'reports' && <div className="reports-layout">
        <section className="report-preview"><div className="report-wordmark">FIRE / ATLAS</div><span className="eyebrow">Selection report</span><h2>Fire activity<br/>summary.</h2><p>{areaName}</p><span className="report-period">{rangeLabel}</span><div className="report-total"><span>Total detections</span><strong>{value(total)}</strong><small>{hasDaily ? fmt(storedDays) + (storedDays === 1 ? ' day with records' : ' days with records') : 'Stored aggregate observations'}</small></div><span className="report-preview-note">{sample ? 'Includes demonstration data' : 'Your applied region and dates'}</span></section>
        <Panel title="Download reports and data" eyebrow="Exports"><div className="report-downloads">{reportRows.map(report => <div className="report-row" key={report.title}><span className="report-icon"><Icon name={report.icon}/></span><div><h3>{report.title}<span>{report.format}</span></h3><p>{report.description}</p></div><button className="subtle-button" disabled={!report.enabled} onClick={report.action} aria-label={(report.format === 'PDF' ? 'Print ' : 'Download ') + report.title}><Icon name={report.format === 'PDF' ? 'document' : 'reports'} size={17}/>{report.format === 'PDF' ? 'Print / PDF' : 'Download'}</button></div>)}</div><p className="panel-note">Exports use the applied region and dates shown above. Unavailable datasets cannot be exported.</p></Panel>
        <Panel title="Included in this selection" className="report-details"><dl className="summary-list"><div><dt>Region</dt><dd>{areaName}</dd></div><div><dt>Bounds · W, S, E, N</dt><dd>{boundsLabel}</dd></div><div><dt>Period</dt><dd>{rangeLabel}</dd></div><div><dt>Observations</dt><dd>All available detections</dd></div><div><dt>Coverage</dt><dd>{hasDaily ? fmt(storedDays) + (storedDays === 1 ? ' day with records' : ' days with records') : 'Unavailable'}</dd></div></dl><p className="panel-note">Detections are not unique fires. Missing periods remain unknown.</p></Panel>
      </div>}

      <footer className="atlas-footer"><span>Fire Atlas <span className="footer-separator">/</span> NASA FIRMS observations</span><span>{sample ? 'Demonstration data' : 'Regional fire activity'}</span></footer>
    </main>
    <section className="print-report" aria-label="Printable selection summary">
      <div className="report-wordmark">FIRE / ATLAS</div><h1>Fire activity summary</h1><h2>{areaName}</h2><p>{rangeLabel}</p><p>Bounds (west, south, east, north): {boundsLabel}</p>{sample && <p>Demonstration data is included. This report does not represent current fire conditions.</p>}
      <dl><dt>Total detections</dt><dd>{fmt(total)}</dd><dt>Mean fire radiative power</dt><dd>{fmt(mean)}{mean != null ? ' MW' : ''}</dd><dt>Observations with FRP</dt><dd>{fmt(hasDaily ? totals.frpCount : null)}</dd><dt>Days with records</dt><dd>{fmt(hasDaily ? storedDays : null)}</dd><dt>Latest stored day</dt><dd>{dateLabel(latest)}</dd></dl>
      <p>Source: stored NASA FIRMS observations. All available observations are included. Counts are detections, not unique fires. Missing periods indicate unknown coverage; they are not treated as zero. FRP is an observation-weighted mean, not fire size. This summary uses aggregate totals, not the limited map record set.</p>
    </section>
    {about && <AboutDialog onClose={() => setAbout(false)}/>}
  </div>;
}
