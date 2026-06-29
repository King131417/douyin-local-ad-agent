#!/usr/bin/env python3
"""Run a 30-day backfill of all ad data."""
import sys, os, logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env
from pathlib import Path
env_path = Path(__file__).parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip("'\""))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

from src.pipeline.etl import ETLPipeline
from datetime import date, timedelta

pipeline = ETLPipeline()
end = date.today()
start = end - timedelta(days=29)

print(f"=== Full backfill: {start} ~ {end} ===")
result = pipeline.run_date_range(start, end)
print(f"=== DONE: {sum(result.values())} rows ===")
