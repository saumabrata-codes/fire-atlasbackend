/** Normalize database aggregate decimals at the API boundary. */
export function normalizeActivityBucket(row: {
  period_start: string; total: unknown; modis: unknown; viirs: unknown;
  frp_sum_mw?: unknown; frp_mean_mw?: unknown; frp_observation_count?: unknown;
}) {
  return { ...row,
    total: Number(row.total ?? 0), modis: Number(row.modis ?? 0), viirs: Number(row.viirs ?? 0),
    frp_sum_mw: row.frp_sum_mw == null ? null : Number(row.frp_sum_mw),
    frp_mean_mw: row.frp_mean_mw == null ? null : Number(row.frp_mean_mw),
    frp_observation_count: Number(row.frp_observation_count ?? 0),
  };
}
