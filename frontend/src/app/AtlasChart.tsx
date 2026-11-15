import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, LineChart } from 'echarts/charts';
import { AriaComponent, GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { ActivityBucket, Hotspot } from '../lib/api';

echarts.use([BarChart, LineChart, AriaComponent, GridComponent, TooltipComponent, CanvasRenderer]);

type ChartRow = Pick<ActivityBucket, 'period_start' | 'total'>;
type Props = {
  type: 'bar' | 'line' | 'distribution';
  rows?: ChartRow[];
  features?: Hotspot[];
  period?: 'day' | 'month';
};

const accent = '#ae5951';
const number = new Intl.NumberFormat('en', { maximumFractionDigits: 1 });

// Explicit nulls break lines across missing periods; missing coverage is never zero.
function withCoverageGaps(rows: ChartRow[], period: Props['period']): ChartRow[] {
  return rows.flatMap((row, index) => {
    if (!index || !period) return [row];
    const previous = new Date(rows[index - 1].period_start);
    const current = new Date(row.period_start);
    const gap = period === 'day'
      ? current.getTime() - previous.getTime() > 86400000
      : (current.getUTCFullYear() - previous.getUTCFullYear()) * 12 + current.getUTCMonth() - previous.getUTCMonth() > 1;
    return gap ? [{ period_start: 'Coverage gap', total: NaN }, row] : [row];
  });
}

export default function AtlasChart({ type, rows = [], features = [], period }: Props) {
  const chartRows = withCoverageGaps(rows, period);
  let labels = chartRows.map(row => /^\d{4}-\d{2}-\d{2}/.test(row.period_start)
    ? row.period_start.slice(0, period === 'month' ? 7 : 10) : row.period_start);
  let values: (number | null)[] = chartRows.map(row => Number.isFinite(row.total) ? row.total : null);

  if (type === 'distribution') {
    const edges = [0, 0.1, 1, 10, 100, 1000, Infinity];
    labels = ['0–0.1', '0.1–1', '1–10', '10–100', '100–1,000', '≥ 1,000'];
    const frp = features.map(feature => feature.properties.frp)
      .filter((value): value is number => value != null && Number.isFinite(value) && value >= 0);
    values = edges.slice(0, -1).map((min, index) => frp.filter(value => value >= min && value < edges[index + 1]).length);
  }

  const isLine = type === 'line';
  const series = [{
    name: type === 'distribution' ? 'Loaded observations' : 'Total detections',
    type: isLine ? 'line' : 'bar',
    data: values,
    barMaxWidth: type === 'distribution' ? 52 : 18,
    connectNulls: false,
    showSymbol: values.length <= 24,
    symbol: 'circle',
    symbolSize: 5,
    lineStyle: { color: accent, width: 2 },
    itemStyle: { color: accent, borderRadius: isLine ? 0 : [3, 3, 0, 0] },
    emphasis: { itemStyle: { color: '#84433e' } },
    ...(isLine ? { areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
      { offset: 0, color: '#ae595122' }, { offset: 1, color: '#ae595102' },
    ]) } } : {}),
  }];

  return <div className="atlas-chart" role="img" aria-label={type === 'distribution'
    ? 'Fire radiative power distribution of loaded observations, in megawatts.'
    : 'Total detections across stored periods. Missing periods have unknown coverage.'}>
    <ReactEChartsCore echarts={echarts} notMerge option={{
      animation: false,
      backgroundColor: 'transparent',
      textStyle: { fontFamily: 'Inter, Segoe UI, sans-serif' },
      aria: { enabled: true },
      grid: { top: 25, left: 12, right: 20, bottom: 12, containLabel: true },
      tooltip: {
        trigger: 'axis', confine: true,
        backgroundColor: '#ffffff', borderColor: '#e6e3de', borderWidth: 1, padding: [12, 16],
        textStyle: { color: '#292b2a', fontSize: 12 },
        extraCssText: 'border-radius:10px;box-shadow:0 8px 28px #292b2a12;',
        axisPointer: { type: isLine ? 'line' : 'shadow', lineStyle: { color: '#d5d0c9' }, shadowStyle: { color: '#292b2a04' } },
        valueFormatter: (value: unknown) => value == null || !Number.isFinite(Number(value)) ? 'Unknown coverage' : number.format(Number(value)),
      },
      xAxis: {
        type: 'category', data: labels, boundaryGap: !isLine,
        axisLine: { lineStyle: { color: '#e6e3de' } }, axisTick: { show: false },
        axisLabel: { color: '#747771', fontSize: 10, margin: 14, hideOverlap: true },
      },
      yAxis: {
        type: 'value', minInterval: 1,
        splitLine: { lineStyle: { color: '#efede9', type: 'dashed' } },
        axisLabel: { color: '#747771', fontSize: 10, margin: 12,
          formatter: (value: number) => Intl.NumberFormat('en', { notation: 'compact' }).format(value) },
      },
      series,
    }} style={{ height: 260, width: '100%' }}/>
  </div>;
}
