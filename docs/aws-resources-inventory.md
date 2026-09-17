# Inventaire des ressources AWS - Compte 551656632516

**Compte AWS :** 551656632516  
**Région :** eu-central-1  
**Projet :** Data Connect Monitoring (DCM)  
**Date d'inventaire :** 17 avril 2026

---

## Compute

### Lambda Functions (2)

| Fonction | Runtime | Mémoire |
|----------|---------|---------|
| dcm-ingestion-api | Python 3.12 | 256 MB |
| lbdAuth-dcm-api-entraid | Node.js 18.x | 128 MB |

### EC2 Instances (1)

| Instance ID | Nom | Type | État |
|-------------|-----|------|------|
| i-00b14270d91fbab82 | awsd-dcm-ec2linux01 | t3.medium | running |

### ECS (1 cluster)

| Cluster | Services |
|---------|----------|
| awsd-ecscluster-dcm-backend | Aucun service actif |

---

## Storage

### S3 Buckets (6)

| Bucket |
|--------|
| awsd-cloudfront-logs-dcm-statics |
| awsd-dcm-awsd-dcm-webapp-files-bucket |
| awsd-dcm-dcm-databricks-workspace-bucket |
| awsd-dcm-terraform-states-bucket |
| s3-alzp-551656632516-eu-central-1-pf-security-logs |
| s3-alzp-551656632516-eu-west-1-pf-security-logs |

### DynamoDB

Aucune table.

### RDS

Aucune instance, aucun cluster.

---

## Networking

### VPC (1)

| VPC ID | Nom | CIDR |
|--------|-----|------|
| vpc-088e0d84c5bfa57c7 | vpc-alzp-eu-central-1 | 10.241.194.128/26 |

### Subnets (3)

| Subnet ID | Nom | AZ | CIDR |
|-----------|-----|----|------|
| subnet-0cd3850bf139eb40e | snet-alzp-eu-central-1-tgw-euc1-az2 | eu-central-1a | 10.241.194.144/28 |
| subnet-01369e4aa336c4e54 | awsd-subnet-dcm-rt-pub-network-1 | eu-central-1c | 10.241.194.176/28 |
| subnet-01e67e66934a67c18 | awsd-subnet-dcm-nrt-pub-network-1 | eu-central-1c | 100.64.0.0/24 |

### API Gateway (1)

| ID | Nom | Type |
|----|-----|------|
| cxtkvrfzud | dcm-api-d | REST |

### CloudFront (1)

| Distribution ID | Alias | Domain | Statut |
|-----------------|-------|--------|--------|
| EQ7G8LQ97M10H | dcm.alzp.tgscloud.net | d2exih436g1gm1.cloudfront.net | Deployed |

### VPC Endpoints (8)

| Type | Service |
|------|---------|
| Gateway | com.amazonaws.eu-central-1.s3 |
| Interface | com.amazonaws.eu-central-1.secretsmanager |
| Interface | com.amazonaws.eu-central-1.logs |
| Interface | com.amazonaws.eu-central-1.execute-api |
| Interface | com.amazonaws.eu-central-1.sqs |
| Interface | com.amazonaws.eu-central-1.kms |
| Interface | com.amazonaws.vpce.eu-central-1.vpce-svc-081f78503812597f7 |
| Interface | com.amazonaws.vpce.eu-central-1.vpce-svc-08e5dfca9572c85c4 |

---

## Sécurité

### KMS Keys (7)

| Key ID |
|--------|
| 14309746-38f5-4786-9810-2db5a7bd49d6 |
| 3b1aa988-b575-4aed-b7bf-b69a15d3fff5 |
| 45471cf7-2eff-4b61-a1a1-0c545fc8652b |
| 6c1e647f-807c-4820-94e5-95f87fbd4cb1 |
| b38e62ed-85c6-4f9d-bb5a-4158fb70b8ba |
| e592775b-1482-4d33-8583-32646cd56f0a |
| f3f949e5-0dcd-469b-8277-d70b70acb713 |

### WAF Web ACLs (3)

| Nom |
|-----|
| FMManagedWebACLV2-fwmpol-alzp-eu-central-1-ShieldAdvancedPolicy |
| FMManagedWebACLV2-fwmpol-alzp-eu-central-1-WAFPolicy |
| FMManagedWebACLV2-fwmpol-alzp-eu-central-1-WAFPolicy-apigw |

### Secrets Manager (3)

| Secret |
|--------|
| awsd-dcm-db-credentials |
| awsd-dcm-api-keys |
| awsd-dcm-entraid-client-secret |

### Security Groups (7)

| Nom | Group ID |
|-----|----------|
| awsd-sg-dcm-dcm-databricks-sg | sg-01e03d54cd95f1b4d |
| awsd-sg-dcm-endpoint_interface | sg-07951cd31650647bb |
| awsd-sg-dcm-ec2linux01 | sg-037ad834a042f7d04 |
| awsd-sg-dcm-awsd-sg-dcm-ecs-backend | sg-0bfab85aca054fa9c |
| awsd-sg-dcm-alb-sg-dcm | sg-081c3f4ca476e107c |
| awsd-sg-dcm-ingestion | sg-0a7a77e1960dcd35d |
| default | sg-0414314c9c7228494 |

---

## Messaging

### SQS Queues (2)

| Queue |
|-------|
| dcm-ingestion |
| dcm-ingestion-dlq (Dead Letter Queue) |

### SNS Topics

Aucun topic.

---

## Observabilité

### CloudWatch Log Groups (8)

| Log Group |
|-----------|
| /aws/apigateway/welcome |
| /aws/lambda/dcm-ingestion-api |
| /aws/lambda/lambdaAuthorizerdcm-api |
| /awsd/cw/dcm/kms-dcm-encryption/logGroup |
| /awsd/cw/dcm/sqs-dcm-ingestion/logGroup |
| /ecs/dcm-backend |
| API-Gateway-Execution-Logs_cxtkvrfzud/dev |
| aws-access-logs-dcm-api-d |

---

## IAM Roles custom (11)

| Rôle |
|------|
| awsd-iamrole-dcm-dcm-api-authorizer |
| awsd-iamrole-dcm-dcm-backend-scheduler |
| awsd-iamrole-dcm-ec2linux-ssm01 |
| awsd-iamrole-dcm-ec2linux01 |
| awsd-iamrole-dcm-guardduty-dcm-databricks-workspace |
| awsd-iamrole-dcm-guardduty-terraform-states |
| awsd-role-dcm-backend-dcm-backend-ecsexc |
| awsd-role-dcm-backend-dcm-backend-ecstsk |
| awsd-role-dcm-ingestion |
| awsd-role-dcm-LambdaAuthorizer |
| dcm-databricks-cross-account-role |
