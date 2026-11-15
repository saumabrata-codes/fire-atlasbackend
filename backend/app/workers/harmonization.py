"""Background raw-to-analytics processor, independent of the FIRMS collector."""
from __future__ import annotations

import logging
import time

from sqlalchemy.exc import SQLAlchemyError

from app.database.repositories.harmonization import pending_source_file_ids, process_source_file
from app.database.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fireatlas.harmonization")


def run_worker(poll_seconds: int = 10) -> None:
    log.info("Raw-to-analytics harmonization worker started")
    while True:
        try:
            with SessionLocal() as db:
                pending = pending_source_file_ids(db, limit=1)
            if not pending:
                time.sleep(poll_seconds)
                continue
            result = process_source_file(pending[0])
            log.info("Harmonized source file %s: %s", pending[0], result)
        except SQLAlchemyError:
            log.exception("Database unavailable; retrying")
            time.sleep(poll_seconds)
        except Exception:
            log.exception("Source file harmonization failed; retrying shortly")
            time.sleep(poll_seconds)


if __name__ == "__main__":
    run_worker()
