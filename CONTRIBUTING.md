# Development notes

- Preserve sensor identity and source fields through ingestion.
- Treat MODIS and VIIRS confidence values as source-specific categories; do not compare them as if they had the same scale.
- Keep raw source files, checksums, and manifests separate from the database.
- Never interpret missing coverage as zero detections or detection counts as unique fires.
- Keep NASA credentials in the backend environment only.
- Add unit checks for parsers and scientific functions using small fixtures with known results.
