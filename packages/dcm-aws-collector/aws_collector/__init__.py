"""DCM AWS Collector — collects KPI metrics from AWS services.

This package implements the AWS-side monitoring agent for the Data Connect
Monitoring (DCM) platform.  It runs as a one-shot **ECS Fargate** task
triggered every 5 minutes by an EventBridge Scheduler rule.

Architecture
------------
- AWS SDK calls (boto3) are synchronous; they are bridged to the async event
  loop via :func:`~aws_collector._aws_utils.run_sync`.
- Credentials are loaded from **AWS Secrets Manager** at startup via
  :class:`~aws_collector.config.AWSCollectorConfig`.
- Each collector targets one AWS service family and produces a
  :class:`~dcm_commons.metrics.MetricPayload` which is forwarded to the DCM
  ingestion layer (Apigee → Lambda → SQS → Databricks Lakebase).

Collectors shipped
------------------
- :class:`~aws_collector.collectors.GlueCollector` — Glue job runs + crawlers
- :class:`~aws_collector.collectors.EMRCollector` — EMR cluster states
- :class:`~aws_collector.collectors.RDSCollector` — RDS / Aurora instances
- :class:`~aws_collector.collectors.CostExplorerCollector` — Cost Explorer + Budgets
- :class:`~aws_collector.collectors.RedshiftCollector` — Redshift clusters
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
