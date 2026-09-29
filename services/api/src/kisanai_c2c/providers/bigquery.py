"""Publishes a node's shareable, k-anonymous data to BigQuery for BRICS AgriN data sharing.

Each node writes to its own dataset in its own region (data stays in the country); the datasets
are offered to other countries' nodes through a BigQuery Analytics Hub exchange. Nothing here
identifies a farmer, a farm or a location below district level.
"""

from __future__ import annotations

from typing import Any

from ..settings import Settings, get_settings

TABLES: dict[str, list[tuple[str, str]]] = {
    "crop_health_signals": [("node_id", "STRING"), ("subdivision_code", "STRING"), ("district", "STRING"), ("crop", "STRING"),
                            ("category", "STRING"), ("reports", "INT64"), ("window_days", "INT64"), ("published_at", "TIMESTAMP")],
    "crop_calendars": [("node_id", "STRING"), ("pack_id", "STRING"), ("pack_version", "INT64"), ("subdivision_code", "STRING"),
                       ("region_name", "STRING"), ("crop_id", "STRING"), ("scientific_name", "STRING"), ("season", "STRING"),
                       ("sowing_start", "STRING"), ("sowing_end", "STRING"), ("irrigation_required", "BOOL"),
                       ("review_status", "STRING"), ("published_at", "TIMESTAMP")],
    "practice_outcomes": [("node_id", "STRING"), ("practice_code", "STRING"), ("outcomes_reported", "INT64"), ("worked", "INT64"),
                          ("partly", "INT64"), ("did_not_work", "INT64"), ("published_at", "TIMESTAMP")],
}


class BigQueryUnavailable(RuntimeError):
    pass


class BigQueryPublisher:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def publish(self, tables: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
        if not (self.settings.bigquery_dataset and self.settings.google_cloud_project):
            raise BigQueryUnavailable("BIGQUERY_DATASET and GOOGLE_CLOUD_PROJECT are required to publish")
        from google.cloud import bigquery

        client = bigquery.Client(project=self.settings.google_cloud_project)
        dataset_ref = bigquery.Dataset(f"{self.settings.google_cloud_project}.{self.settings.bigquery_dataset}")
        dataset_ref.location = self.settings.bigquery_location
        dataset_ref.description = f"BRICS AgriN shared data published by {self.settings.node_label} ({self.settings.node_id})"
        client.create_dataset(dataset_ref, exists_ok=True)
        written: dict[str, int] = {}
        for name, rows in tables.items():
            schema = [bigquery.SchemaField(field, kind) for field, kind in TABLES[name]]
            job = client.load_table_from_json(
                rows, f"{self.settings.google_cloud_project}.{self.settings.bigquery_dataset}.{name}",
                job_config=bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_TRUNCATE"),
            )
            job.result(timeout=120)
            written[name] = len(rows)
        return written
