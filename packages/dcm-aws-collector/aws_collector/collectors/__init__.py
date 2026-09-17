"""AWS resource collectors — public surface of the ``aws_collector.collectors`` package.

Each collector is a concrete implementation of
:class:`~dcm_commons.collectors.base.BaseCollector` that targets a specific
AWS service family.

Collectors
----------
GlueCollector
    AWS Glue job runs and crawler last-crawl results → ``PIPELINE`` domain.
GlueActivityRunCollector
    AWS Glue workflow node-level and standalone job run details → ``ACTIVITY_RUN`` domain.
EMRCollector
    Amazon EMR cluster state snapshots → ``CLUSTER`` domain.
RDSCollector
    Amazon RDS / Aurora DB instance health and CloudWatch metrics → ``DATABASE`` domain.
CostExplorerCollector
    AWS Cost Explorer daily costs by service with budget enrichment → ``COST`` domain.
RedshiftCollector
    Amazon Redshift cluster health and CloudWatch metrics → ``DATABASE`` domain.
IAMUserCollector
    AWS IAM user snapshots with groups, policies, and last-activity timestamps → ``USER`` domain.
ConfigStandardCheckCollector
    AWS Config Rule compliance evaluation results → ``STANDARD_CHECK`` domain.
"""

from aws_collector.collectors.config_compliance import ConfigStandardCheckCollector
from aws_collector.collectors.cost_explorer import CostExplorerCollector
from aws_collector.collectors.emr import EMRCollector
from aws_collector.collectors.glue import GlueCollector
from aws_collector.collectors.glue_activity_runs import GlueActivityRunCollector
from aws_collector.collectors.iam_users import IAMUserCollector
from aws_collector.collectors.rds import RDSCollector
from aws_collector.collectors.redshift import RedshiftCollector

__all__ = [
    "ConfigStandardCheckCollector",
    "CostExplorerCollector",
    "EMRCollector",
    "GlueCollector",
    "GlueActivityRunCollector",
    "IAMUserCollector",
    "RDSCollector",
    "RedshiftCollector",
]
