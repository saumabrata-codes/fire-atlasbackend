# Interpretation and current limitations

- A FIRMS hotspot is a satellite detection, not necessarily a unique fire.
- Detection counts from MODIS and VIIRS are kept separate. Their confidence fields and detection characteristics are not treated as directly equivalent.
- The bundled CSVs are deterministic demonstration fixtures, not verified NASA observations.
- Missing observations are not treated as zero activity.
- Historical collection is available as an opt-in, resumable worker. It is paused until frontend acceptance and must not run during UI work.
- Harmonization aligns daily sensor-specific counts on a shared grid; it does not calibrate MODIS and VIIRS to a common physical scale.
- A simple recent-bucket spike screen is descriptive only. Formal anomaly scores still require approved baselines and validation.
- FIRMS hotspot CSVs contain detections, not imagery scenes or damage reports. NASA Worldview/GIBS links provide visual context, and local disruption must not be inferred from hotspots alone.
