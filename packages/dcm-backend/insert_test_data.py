#!/usr/bin/env python3
"""
Insert test data into Lakebase PostgreSQL for frontend testing.

⚠️  ATTENTION: Ces données sont des DONNÉES DE TEST uniquement !
    Elles sont marquées avec "[TEST]" pour faciliter l'identification.

Usage:
    cd packages/dcm-backend
    python insert_test_data.py
"""

import asyncio
import asyncpg
import os
import ssl
from datetime import datetime, timedelta
import random
import uuid

# Connection parameters (from environment / .env — never hardcode secrets)
DB_CONFIG = {
    "host": os.environ["DCM_DB_HOST"],
    "port": int(os.environ.get("DCM_DB_PORT", "5432")),
    "database": os.environ.get("DCM_DB_NAME", "databricks_postgres"),
    "user": os.environ["DCM_DB_USER"],
    "password": os.environ["DCM_DB_PASSWORD"],
}

# Test Landing Zones
TEST_LZS = [
    {"lz_id": "lz-azure-datasquad-test", "cloud": "azure", "sub": "sub-azure-test-001", "region": "eu-west-1", "env": "dev", "ba": "DataSquad"},
    {"lz_id": "lz-aws-datasquad-test", "cloud": "aws", "sub": "123456789012", "region": "eu-central-1", "env": "dev", "ba": "DataSquad"},
    {"lz_id": "lz-azure-finance-test", "cloud": "azure", "sub": "sub-azure-test-002", "region": "eu-west-1", "env": "prod", "ba": "Finance"},
    {"lz_id": "lz-aws-marketing-test", "cloud": "aws", "sub": "987654321098", "region": "us-east-1", "env": "prod", "ba": "Marketing"},
]

# Test Services for costs
TEST_SERVICES = {
    "azure": ["Azure Data Factory", "Azure Databricks", "Azure SQL Database", "Azure Storage", "Azure Key Vault"],
    "aws": ["AWS Glue", "Amazon EMR", "Amazon RDS", "Amazon S3", "AWS Secrets Manager"],
}

# Test pipeline names
TEST_PIPELINES = {
    "azure": ["[TEST] ADF_Ingest_Sales", "[TEST] ADF_Transform_Finance", "[TEST] ADF_Export_Reports", "[TEST] ADF_Daily_ETL"],
    "aws": ["[TEST] Glue_Ingest_Customers", "[TEST] Glue_Transform_Orders", "[TEST] Glue_Export_Analytics", "[TEST] Glue_Hourly_Sync"],
}

# Test database names
TEST_DATABASES = {
    "azure": [("[TEST] sqldb-sales-dev", "Azure SQL Database"), ("[TEST] sqldb-finance-prod", "Azure SQL Database"), ("[TEST] cosmos-orders", "CosmosDB")],
    "aws": [("[TEST] rds-customers", "PostgreSQL"), ("[TEST] rds-inventory", "MySQL"), ("[TEST] aurora-analytics", "Aurora PostgreSQL")],
}

# Test compute clusters
TEST_CLUSTERS = {
    "azure": [("[TEST] dbx-etl-cluster", "interactive"), ("[TEST] dbx-ml-cluster", "job"), ("[TEST] dbx-adhoc", "interactive")],
    "aws": [("[TEST] emr-etl-cluster", "core"), ("[TEST] emr-ml-cluster", "task"), ("[TEST] emr-streaming", "core")],
}

# Test users
TEST_USERS = {
    "azure": [
        {"id": "test-user-001", "name": "[TEST] John Doe", "email": "john.doe.test@company.com", "type": "azure_ad"},
        {"id": "test-user-002", "name": "[TEST] Jane Smith", "email": "jane.smith.test@company.com", "type": "azure_ad"},
        {"id": "test-spn-001", "name": "[TEST] SPN_ETL_Service", "email": None, "type": "spn"},
    ],
    "aws": [
        {"id": "test-iam-001", "name": "[TEST] aws-etl-user", "email": None, "type": "iam_user"},
        {"id": "test-iam-002", "name": "[TEST] aws-admin-user", "email": None, "type": "iam_user"},
        {"id": "test-dbx-001", "name": "[TEST] databricks_user", "email": "dbx.user.test@company.com", "type": "databricks_scim"},
    ],
}


async def get_connection():
    """Create database connection with SSL."""
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    return await asyncpg.connect(
        **DB_CONFIG,
        ssl=ssl_context,
    )


async def insert_dim_landing_zone(conn):
    """Insert test landing zones."""
    print("📍 Inserting dim_landing_zone...")
    
    for lz in TEST_LZS:
        await conn.execute("""
            INSERT INTO dim_landing_zone (lz_id, lz_name, cloud_provider, subscription_or_account_id, region, environment, ba_name, is_current)
            VALUES ($1, $2, $3, $4, $5, $6, $7, TRUE)
            ON CONFLICT (lz_id, valid_from) DO NOTHING
        """, lz["lz_id"], f"[TEST] {lz['ba']} - {lz['cloud'].upper()}", lz["cloud"], lz["sub"], lz["region"], lz["env"], lz["ba"])
    
    print(f"   ✅ {len(TEST_LZS)} landing zones inserted")


async def insert_pipeline_metrics(conn):
    """Insert test pipeline runs."""
    print("🔄 Inserting pipeline_metrics...")
    
    count = 0
    statuses = ["succeeded", "failed", "running", "cancelled"]
    triggers = ["scheduled", "manual", "event"]
    
    for lz in TEST_LZS:
        pipelines = TEST_PIPELINES.get(lz["cloud"], [])
        for pipeline_name in pipelines:
            # Generate 10 runs per pipeline over the last 30 days
            for i in range(10):
                run_id = f"test-run-{uuid.uuid4().hex[:8]}"
                start_time = datetime.now() - timedelta(days=random.randint(1, 30), hours=random.randint(0, 23))
                duration = random.randint(60, 3600)
                status = random.choices(statuses, weights=[70, 15, 10, 5])[0]
                
                end_time = start_time + timedelta(seconds=duration) if status != "running" else None
                error_msg = "[TEST] Pipeline failed due to data validation error" if status == "failed" else None
                
                await conn.execute("""
                    INSERT INTO pipeline_metrics 
                    (pipeline_name, pipeline_id, run_id, cloud_provider, source_lz_id, subscription_or_account_id,
                     status, trigger_type, start_time, end_time, duration_seconds, error_message, tags, collected_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    ON CONFLICT (run_id) DO NOTHING
                """, 
                    pipeline_name, f"pipeline-{uuid.uuid4().hex[:8]}", run_id, 
                    lz["cloud"], lz["lz_id"], lz["sub"],
                    status, random.choice(triggers), start_time, end_time, 
                    float(duration) if status != "running" else None, error_msg,
                    '{"test": true, "source": "insert_test_data.py"}', datetime.now()
                )
                count += 1
    
    print(f"   ✅ {count} pipeline runs inserted")


async def insert_activity_runs(conn):
    """Insert test activity runs."""
    print("⚡ Inserting activity_runs...")
    
    count = 0
    activity_types = ["copy", "databricks_notebook", "lookup", "for_each", "execute_pipeline"]
    statuses = ["succeeded", "failed", "running"]
    
    # Get existing pipeline runs
    runs = await conn.fetch("SELECT run_id, pipeline_name, cloud_provider, source_lz_id, subscription_or_account_id FROM pipeline_metrics WHERE tags->>'test' = 'true' LIMIT 50")
    
    for run in runs:
        # 3-5 activities per pipeline run
        for i in range(random.randint(3, 5)):
            activity_name = f"[TEST] Activity_{i+1}_{random.choice(['Copy', 'Transform', 'Validate', 'Load'])}"
            start_time = datetime.now() - timedelta(hours=random.randint(1, 48))
            duration = random.randint(30, 600)
            status = random.choices(statuses, weights=[80, 15, 5])[0]
            
            await conn.execute("""
                INSERT INTO activity_runs
                (pipeline_run_id, pipeline_name, activity_name, activity_type, cloud_provider, source_lz_id,
                 subscription_or_account_id, status, start_time, end_time, duration_seconds, 
                 rows_read, rows_written, data_read_bytes, data_written_bytes, tags, collected_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                ON CONFLICT (pipeline_run_id, activity_name) DO NOTHING
            """,
                run["run_id"], run["pipeline_name"], activity_name, random.choice(activity_types),
                run["cloud_provider"], run["source_lz_id"], run["subscription_or_account_id"],
                status, start_time, start_time + timedelta(seconds=duration) if status != "running" else None,
                float(duration), random.randint(1000, 100000), random.randint(1000, 100000),
                random.randint(1000000, 100000000), random.randint(1000000, 100000000),
                '{"test": true}', datetime.now()
            )
            count += 1
    
    print(f"   ✅ {count} activity runs inserted")


async def insert_compute_metrics(conn):
    """Insert test compute/cluster metrics."""
    print("🖥️  Inserting compute_metrics...")
    
    count = 0
    states = ["RUNNING", "TERMINATED", "PENDING", "RESIZING"]
    
    for lz in TEST_LZS:
        clusters = TEST_CLUSTERS.get(lz["cloud"], [])
        for cluster_name, cluster_type in clusters:
            # Generate 5 snapshots per cluster over the last 7 days
            for i in range(5):
                collected_at = datetime.now() - timedelta(days=random.randint(0, 7), hours=random.randint(0, 23))
                state = random.choices(states, weights=[60, 25, 10, 5])[0]
                
                await conn.execute("""
                    INSERT INTO compute_metrics
                    (compute_resource_id, resource_name, compute_type, cloud_provider, source_lz_id,
                     subscription_or_account_id, state, num_workers, node_type, spark_version,
                     avg_cpu_utilization_pct, avg_mem_utilization_pct, tags, collected_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                """,
                    f"cluster-{uuid.uuid4().hex[:8]}", cluster_name, cluster_type,
                    lz["cloud"], lz["lz_id"], lz["sub"],
                    state, random.randint(2, 10), "Standard_DS3_v2" if lz["cloud"] == "azure" else "m5.xlarge",
                    "13.3 LTS" if lz["cloud"] == "azure" else "emr-6.10.0",
                    round(random.uniform(10, 95), 2) if state == "RUNNING" else None,
                    round(random.uniform(20, 85), 2) if state == "RUNNING" else None,
                    '{"test": true, "team": "DataSquad"}', collected_at
                )
                count += 1
    
    print(f"   ✅ {count} compute metrics inserted")


async def insert_cost_metrics(conn):
    """Insert test cost metrics."""
    print("💰 Inserting cost_metrics...")
    
    count = 0
    
    for lz in TEST_LZS:
        services = TEST_SERVICES.get(lz["cloud"], [])
        for service in services:
            # Generate costs for the last 3 months
            for month_offset in range(3):
                period_start = (datetime.now() - timedelta(days=30 * month_offset)).replace(day=1).date()
                period_end = (period_start + timedelta(days=31)).replace(day=1) - timedelta(days=1)
                
                cost = round(random.uniform(100, 5000), 2)
                budget_limit = round(cost * random.uniform(1.1, 1.5), 2)
                
                await conn.execute("""
                    INSERT INTO cost_metrics
                    (service_name, subscription_or_account_id, cloud_provider, source_lz_id,
                     period_start, period_end, cost_usd, currency, budget_name, budget_limit_usd, budget_consumed_pct)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    ON CONFLICT (service_name, subscription_or_account_id, period_start, period_end) DO NOTHING
                """,
                    f"[TEST] {service}", lz["sub"], lz["cloud"], lz["lz_id"],
                    period_start, period_end, cost, "USD",
                    f"[TEST] Budget {lz['ba']}", budget_limit, round((cost / budget_limit) * 100, 2)
                )
                count += 1
    
    print(f"   ✅ {count} cost metrics inserted")


async def insert_database_metrics(conn):
    """Insert test database metrics."""
    print("🗄️  Inserting database_metrics...")
    
    count = 0
    
    for lz in TEST_LZS:
        databases = TEST_DATABASES.get(lz["cloud"], [])
        for db_name, db_type in databases:
            # Generate 5 snapshots per database
            for i in range(5):
                collected_at = datetime.now() - timedelta(days=random.randint(0, 7), hours=random.randint(0, 23))
                is_available = random.random() > 0.1  # 90% availability
                
                await conn.execute("""
                    INSERT INTO database_metrics
                    (db_id, db_name, db_type, server_name, region, availability_zone, cloud_provider, source_lz_id,
                     subscription_or_account_id, cpu_percent, memory_percent, storage_used_gb, storage_limit_gb,
                     storage_cost_impact_usd, active_connections, is_available, tags, collected_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18)
                """,
                    f"db-{uuid.uuid4().hex[:8]}", db_name, db_type,
                    f"[TEST] server-{lz['cloud']}-{i}", lz["region"], f"{lz['region']}a",
                    lz["cloud"], lz["lz_id"], lz["sub"],
                    round(random.uniform(5, 80), 2) if is_available else None,
                    round(random.uniform(10, 75), 2) if is_available else None,
                    round(random.uniform(10, 500), 2),
                    round(random.uniform(500, 2000), 2),
                    round(random.uniform(10, 200), 2),
                    random.randint(5, 100) if is_available else 0,
                    is_available,
                    '{"test": true}', collected_at
                )
                count += 1
    
    print(f"   ✅ {count} database metrics inserted")


async def insert_security_alerts(conn):
    """Insert test security alerts."""
    print("🚨 Inserting security_alerts...")
    
    count = 0
    severities = ["critical", "high", "medium", "low"]
    statuses = ["active", "resolved", "dismissed"]
    
    alert_templates = [
        ("[TEST] Publicly accessible storage account detected", "Storage account allows public blob access"),
        ("[TEST] Unencrypted database connection", "Database accepts non-SSL connections"),
        ("[TEST] Excessive permissions on service principal", "Service principal has Owner role on subscription"),
        ("[TEST] Missing network security rules", "Virtual network lacks proper NSG configuration"),
        ("[TEST] Outdated TLS version in use", "Resource using TLS 1.0 which is deprecated"),
    ]
    
    for lz in TEST_LZS:
        # Generate 5-10 alerts per LZ
        for i in range(random.randint(5, 10)):
            title, desc = random.choice(alert_templates)
            detected_at = datetime.now() - timedelta(days=random.randint(0, 14), hours=random.randint(0, 23))
            
            await conn.execute("""
                INSERT INTO security_alerts
                (alert_id, title, description, severity, status, cloud_provider, source_lz_id,
                 subscription_or_account_id, detected_at, resource_id, resource_name, resource_type, tags)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                ON CONFLICT (alert_id) DO NOTHING
            """,
                f"test-alert-{uuid.uuid4().hex[:12]}", title, desc,
                random.choice(severities), random.choices(statuses, weights=[50, 40, 10])[0],
                lz["cloud"], lz["lz_id"], lz["sub"],
                detected_at,
                f"/subscriptions/{lz['sub']}/resourceGroups/test-rg/providers/test-resource-{i}",
                f"[TEST] resource-{i}", "Microsoft.Storage/storageAccounts",
                '{"test": true}'
            )
            count += 1
    
    print(f"   ✅ {count} security alerts inserted")


async def insert_user_metrics(conn):
    """Insert test user metrics."""
    print("👥 Inserting user_metrics...")
    
    count = 0
    
    for lz in TEST_LZS:
        users = TEST_USERS.get(lz["cloud"], [])
        for user in users:
            is_active = random.random() > 0.2  # 80% active
            last_activity = datetime.now() - timedelta(days=random.randint(0, 30)) if is_active else None
            
            await conn.execute("""
                INSERT INTO user_metrics
                (user_id, user_name, display_name, cloud_provider, source_lz_id, subscription_or_account_id,
                 user_type, workspace_or_account, is_active, last_activity_at, groups, roles, tags,
                 is_current, collected_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                ON CONFLICT (user_id, source_lz_id, valid_from) DO NOTHING
            """,
                user["id"], user["name"], user["name"],
                lz["cloud"], lz["lz_id"], lz["sub"],
                user["type"], f"[TEST] workspace-{lz['ba'].lower()}",
                is_active, last_activity,
                '["[TEST] data-engineers", "[TEST] developers"]',
                '["reader", "contributor"]',
                '{"test": true}', True, datetime.now()
            )
            count += 1
    
    print(f"   ✅ {count} user metrics inserted")


async def insert_standard_checks(conn):
    """Insert test standard checks (governance/compliance)."""
    print("✅ Inserting standard_checks...")
    
    count = 0
    check_states = ["compliant", "non_compliant", "not_applicable"]
    check_effects = ["Audit", "Deny", "AuditIfNotExists"]
    
    check_templates = [
        ("[TEST] Require encryption at rest", "check-encrypt-001"),
        ("[TEST] Require HTTPS only", "check-https-001"),
        ("[TEST] Deny public IP addresses", "check-publicip-001"),
        ("[TEST] Require tagging policy", "check-tags-001"),
        ("[TEST] Enforce minimum TLS version", "check-tls-001"),
    ]
    
    for lz in TEST_LZS:
        for check_name, check_id in check_templates:
            # Generate 3 evaluations per check
            for i in range(3):
                evaluated_at = datetime.now() - timedelta(days=random.randint(0, 7), hours=random.randint(0, 23))
                state = random.choices(check_states, weights=[60, 30, 10])[0]
                
                await conn.execute("""
                    INSERT INTO standard_checks
                    (check_id, check_name, cloud_provider, source_lz_id, subscription_or_account_id,
                     check_state, resource_id, resource_name, resource_type, check_effect, evaluated_at, tags)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (check_id, resource_id, source_lz_id, evaluated_at) DO NOTHING
                """,
                    f"{check_id}-{lz['lz_id']}", check_name, lz["cloud"], lz["lz_id"], lz["sub"],
                    state,
                    f"/test/resource/{uuid.uuid4().hex[:8]}",
                    f"[TEST] Resource {i+1}",
                    "Microsoft.Storage/storageAccounts" if lz["cloud"] == "azure" else "AWS::S3::Bucket",
                    random.choice(check_effects), evaluated_at,
                    '{"test": true}'
                )
                count += 1
    
    print(f"   ✅ {count} standard checks inserted")


async def insert_collection_runs(conn):
    """Insert test collection runs (audit trail)."""
    print("📊 Inserting collection_runs...")
    
    count = 0
    domains = ["pipeline", "compute", "cost", "database", "security", "user", "standard_check"]
    
    for lz in TEST_LZS:
        for domain in domains:
            # Generate 3 collection runs per domain
            for i in range(3):
                collected_at = datetime.now() - timedelta(days=random.randint(0, 7), hours=random.randint(0, 12))
                
                await conn.execute("""
                    INSERT INTO collection_runs
                    (run_id, source_lz_id, cloud_provider, subscription_or_account_id, domain, collected_at, metrics_count)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (run_id) DO NOTHING
                """,
                    f"test-collection-{uuid.uuid4().hex[:12]}", lz["lz_id"], lz["cloud"], lz["sub"],
                    domain, collected_at, random.randint(10, 100)
                )
                count += 1
    
    print(f"   ✅ {count} collection runs inserted")


async def main():
    """Insert all test data."""
    print("=" * 60)
    print("🧪 DCM Test Data Insertion Script")
    print("=" * 60)
    print()
    print("⚠️  ATTENTION: Ces données sont des DONNÉES DE TEST !")
    print("    Elles sont marquées avec '[TEST]' dans les noms.")
    print()
    
    conn = await get_connection()
    print("✅ Connected to Lakebase PostgreSQL")
    print()
    
    try:
        # Insert in order (respect dependencies)
        await insert_dim_landing_zone(conn)
        await insert_pipeline_metrics(conn)
        await insert_activity_runs(conn)
        await insert_compute_metrics(conn)
        await insert_cost_metrics(conn)
        await insert_database_metrics(conn)
        await insert_security_alerts(conn)
        await insert_user_metrics(conn)
        await insert_standard_checks(conn)
        await insert_collection_runs(conn)
        
        print()
        print("=" * 60)
        print("✅ ALL TEST DATA INSERTED SUCCESSFULLY!")
        print("=" * 60)
        print()
        print("📝 Note: Les données de test sont identifiables par:")
        print("   - Préfixe '[TEST]' dans les noms")
        print("   - Tag JSON: {\"test\": true}")
        print("   - LZ IDs: lz-*-test")
        print()
        print("🧹 Pour supprimer les données de test:")
        print("   DELETE FROM pipeline_metrics WHERE tags->>'test' = 'true';")
        print("   DELETE FROM activity_runs WHERE tags->>'test' = 'true';")
        print("   DELETE FROM compute_metrics WHERE tags->>'test' = 'true';")
        print("   DELETE FROM cost_metrics WHERE service_name LIKE '[TEST]%';")
        print("   DELETE FROM database_metrics WHERE tags->>'test' = 'true';")
        print("   DELETE FROM security_alerts WHERE tags->>'test' = 'true';")
        print("   DELETE FROM user_metrics WHERE tags->>'test' = 'true';")
        print("   DELETE FROM standard_checks WHERE tags->>'test' = 'true';")
        print("   DELETE FROM dim_landing_zone WHERE lz_id LIKE '%-test';")
        print("   DELETE FROM collection_runs WHERE run_id LIKE 'test-%';")
        
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
