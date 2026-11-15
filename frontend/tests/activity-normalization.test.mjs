import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeActivityBucket } from '../src/lib/normalizeActivity.ts';
test('database string decimals aggregate numerically and null sensors stay zero', () => {
  const rows = [
    { period_start: '2000-11-01', total: '107616', modis: '107616', viirs: null, frp_sum_mw: '4538841.9', frp_observation_count: '107616' },
    { period_start: '2026-11-13', total: '77', modis: '8', viirs: '69', frp_sum_mw: '154', frp_observation_count: '77' },
  ].map(normalizeActivityBucket);
  assert.equal(rows.reduce((sum, r) => sum + r.total, 0), 107693);
  assert.equal(rows.reduce((sum, r) => sum + r.modis, 0), 107624);
  assert.equal(rows.reduce((sum, r) => sum + r.viirs, 0), 69);
  assert.equal(rows[0].frp_sum_mw, 4538841.9);
  assert.equal(rows[0].frp_observation_count, 107616);
  assert.equal(rows[0].frp_mean_mw, null);
});
test('missing FRP remains unknown while explicit zero is retained', () => {
  const r = normalizeActivityBucket({period_start:'2026-11-13', total:0, modis:0, viirs:0, frp_mean_mw:0});
  assert.equal(r.frp_mean_mw, 0);
  assert.equal(r.frp_sum_mw, null);
});
