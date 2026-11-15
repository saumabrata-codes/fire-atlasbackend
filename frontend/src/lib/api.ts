import { normalizeActivityBucket } from './normalizeActivity';
export type Sensor = 'MODIS' | 'VIIRS';

export interface Hotspot {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: { id: string; sensor: Sensor; satellite: string; product: string; confidence: string | null; frp: number | null; acq_datetime: string; [key: string]: unknown };
}
export interface GridCellFeature {
  type: 'Feature';
  geometry: { type: 'Polygon'; coordinates: number[][][] };
  properties: { cell_key: string; sensor: 'ALL' | Sensor; modis: number; viirs: number; total: number; resolution: string };
}

export interface Summary {
  sample_mode: boolean;
  as_of: string | null;
  total_detections: number;
  modis_detections: number;
  viirs_detections: number;
  mean_frp: number;
  observations: string;
}

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1').replace(/\/$/, '');
export const csvReportUrl = `${API_BASE}/reports/observations.csv`;
export const pdfReportUrl = `${API_BASE}/reports/summary.pdf`;

export function getReportUrl(format: 'csv' | 'pdf', sensor: 'ALL' | Sensor, filters: ObservationFilters = {}): string {
  const query = new URLSearchParams({ sensor });
  if (filters.start) query.set('start', filters.start);
  if (filters.end) query.set('end', filters.end);
  if (filters.bbox) ['west', 'south', 'east', 'north'].forEach((key, index) => query.set(key, String(filters.bbox?.[index])));
  const path = format === 'csv' ? '/reports/observations.csv' : '/reports/summary.pdf';
  return `${API_BASE}${path}?${query.toString()}`;
}

export interface DailyActivity { date: string; modis: number; viirs: number; total: number }
export interface MonthlyActivity { month: string; modis: number; viirs: number; total: number }
export interface YearlyActivity { year: string; modis: number; viirs: number; total: number }
export interface SensorMetrics { detections: number; mean_frp: number | null; max_frp: number | null; satellites: string[]; products: string[]; confidence_categories: Record<string, number> }
export interface IngestionJob { id: string; product_id: string; status: string; records_downloaded: number; records_validated: number; records_processed: number; started_at: string; completed_at: string | null }
export interface ArchivedSource { sensor: Sensor; product: string; file: string; year: string; month: string; record_count: number; downloaded_at: string; sha256: string; verified: boolean }
export interface ReportJob { id: string; report_type: string; sensor: string; status: string; records_included: number; output_path: string | null; checksum: string | null; created_at: string | null }
export interface ObservationFilters { start?: string; end?: string; bbox?: [number, number, number, number] }
export interface RegionImage { sensor: Sensor; satellite: string; layer: string; image_url: string }
export interface RegionSummary {
  summary_lines: string[];
  explanation: string | null;
  explanation_source: string;
  sample_mode: boolean;
  data_available: boolean;
  preprocessing: Record<string, unknown> | null;
  imagery: { provider: string; images: RegionImage[]; browse_url: string; note: string };
}
export interface ActivityBucket {
  period_start: string;
  total: number;
  modis: number;
  viirs: number;
  frp_sum_mw?: number | null;
  frp_mean_mw?: number | null;
  frp_observation_count?: number;
  covered_days?: number;
  grid_periods?: number;
}
export interface ActivitySeries {
  period: 'day' | 'month' | 'year';
  source?: string;
  sample_mode: boolean;
  series: ActivityBucket[];
  cross_sensor_calibrated?: false;
  method_note?: string;
  coverage_note?: string;
  preprocessing?: Record<string, unknown> | null;
}
export interface RegionExplanation {
  question: string;
  explanation: string | null;
  explanation_source: string;
  summary_lines: string[];
  data_available: boolean;
  sample_mode: boolean;
  preprocessing: Record<string, unknown> | null;
  note: string;
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
  return response.json() as Promise<T>;
}

export const getSummary = (filters: ObservationFilters = {}) => {
  const query = new URLSearchParams();
  if (filters.start) query.set('start', filters.start);
  if (filters.end) query.set('end', filters.end);
  if (filters.bbox) ['west', 'south', 'east', 'north'].forEach((key, index) => query.set(key, String(filters.bbox?.[index])));
  return get<Summary>(`/overview/summary?${query.toString()}`);
};
function analyticsQuery(filters: ObservationFilters, sensor?: 'ALL' | Sensor, period?: ActivitySeries['period']): string {
  const query = new URLSearchParams();
  if (filters.start) query.set('start', filters.start);
  if (filters.end) query.set('end', filters.end);
  if (sensor) query.set('sensor', sensor);
  if (period) query.set('period', period);
  if (filters.bbox) ['west', 'south', 'east', 'north'].forEach((key, index) => query.set(key, String(filters.bbox?.[index])));
  return query.toString();
}
export const getRegionSummary = (filters: ObservationFilters = {}, sensor: 'ALL' | Sensor = 'ALL') =>
  get<RegionSummary>(`/analytics/region-summary?${analyticsQuery(filters, sensor)}`);
export const getActivitySeries = async (filters: ObservationFilters = {}, sensor: 'ALL' | Sensor = 'ALL', period: ActivitySeries['period'] = 'month') => {
  const result = await get<ActivitySeries>(`/analytics/timeseries?${analyticsQuery(filters, sensor, period)}`);
  // PostgreSQL aggregate decimals can arrive as JSON strings; absent sensors are null.
  return { ...result, series: result.series.map(normalizeActivityBucket) };
};
export const getHarmonizedActivity = (filters: ObservationFilters = {}, period: ActivitySeries['period'] = 'month') =>
  get<ActivitySeries>(`/analytics/harmonized?${analyticsQuery(filters, undefined, period)}`);
export async function askAboutRegion(question: string, filters: ObservationFilters = {}, sensor: 'ALL' | Sensor = 'ALL'): Promise<RegionExplanation> {
  const body: Record<string, unknown> = { question, sensor };
  if (filters.start) body.start = filters.start;
  if (filters.end) body.end = filters.end;
  if (filters.bbox) ["west", "south", "east", "north"].forEach((key, index) => { body[key] = filters.bbox?.[index]; });
  const response = await fetch(`${API_BASE}/analytics/explain`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`);
  return response.json() as Promise<RegionExplanation>;
}
export const getHotspots = (sensor: 'ALL' | Sensor, filters: ObservationFilters = {}) => {
  const query = new URLSearchParams({ sensor });
  if (filters.start) query.set('start', filters.start);
  if (filters.end) query.set('end', filters.end);
  if (filters.bbox) ['west', 'south', 'east', 'north'].forEach((key, index) => query.set(key, String(filters.bbox?.[index])));
  return get<{ sample_mode: boolean; count: number; features: Hotspot[] }>(`/map/hotspots?${query.toString()}`);
};
export const getMapGrid = (sensor: 'ALL' | Sensor, filters: ObservationFilters = {}, limit = 2000, offset = 0) => {
  const query = new URLSearchParams({ sensor, limit: String(limit), offset: String(offset) });
  if (filters.start) query.set('start', filters.start);
  if (filters.end) query.set('end', filters.end);
  if (filters.bbox) ['west', 'south', 'east', 'north'].forEach((key, index) => query.set(key, String(filters.bbox?.[index])));
  return get<{ type: 'FeatureCollection'; source: string; count: number; offset: number; has_more: boolean; next_offset: number | null; preprocessing: Record<string, unknown> | null; coverage_note: string; features: GridCellFeature[] }>(`/map/grid?${query.toString()}`);
};
export const getIngestionStatus = () => get<{ mode: string; firms_configured: boolean; collection_enabled: boolean; sample_records: number; note: string }>('/ingestion/status');
export const getIngestionJobs = () => get<{ jobs: IngestionJob[]; database_available?: boolean }>('/ingestion/jobs');
export const getIngestionArchives = () => get<{ archives: ArchivedSource[] }>('/ingestion/archives');
export const getFirmsAvailability = () => get<{ products: Array<Record<string, string>>; source: string }>('/ingestion/availability');
export const getReportJobs = () => get<{ jobs: ReportJob[]; database_available?: boolean }>('/reports/jobs');
export const getMonthlyActivity = () => get<{ sample_mode: boolean; months: MonthlyActivity[]; coverage_note: string }>('/calendar/monthly');
export const getYearlyActivity = () => get<{ sample_mode: boolean; years: YearlyActivity[]; coverage_note: string }>('/calendar/yearly');
export const getDailyActivity = (filters: ObservationFilters = {}) => {
  const query = new URLSearchParams();
  if (filters.start) query.set('start', filters.start);
  if (filters.end) query.set('end', filters.end);
  return get<{ sample_mode: boolean; days: DailyActivity[]; coverage_note: string }>(`/calendar/daily?${query.toString()}`);
};
export const getSensorComparison = () => get<{ sample_mode: boolean; sensors: { modis: SensorMetrics; viirs: SensorMetrics }; method_note: string }>('/sensors/comparison');
export const getAnomalySummary = (filters: ObservationFilters = {}, sensor: 'ALL' | Sensor = 'ALL') => get<{ available: boolean; covered_days: number; reason: string | null; result?: string; missing_is_zero: boolean }>(`/anomalies/summary?${analyticsQuery(filters, sensor)}`);
export async function requestFirmsSample(sensor: Sensor, bbox: [number, number, number, number]): Promise<{ records_validated: number; stored: boolean; area: string; archive: { path: string; sha256: string }; note: string }> {
  const query = new URLSearchParams({ day_range: '1', west: String(bbox[0]), south: String(bbox[1]), east: String(bbox[2]), north: String(bbox[3]) });
  const response = await fetch(`${API_BASE}/ingestion/sample/${sensor}?${query}`, { method: 'POST' });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || `FIRMS request failed (${response.status})`);
  return body;
}
export async function replayArchivedSource(source: ArchivedSource): Promise<{ records_stored: number; stored: boolean; sha256: string }> {
  const path = [source.sensor, source.product, source.year, source.month, source.file].map(encodeURIComponent).join('/');
  const response = await fetch(`${API_BASE}/ingestion/archive/${path}/replay`, { method: 'POST' });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || `Archive replay failed (${response.status})`);
  return body;
}
