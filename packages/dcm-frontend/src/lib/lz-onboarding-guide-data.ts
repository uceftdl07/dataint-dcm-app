export type GuideRole = 'you' | 'agent' | 'devops';

export interface GuidePhase {
  id: string;
  step: string;
  role: GuideRole;
  title: string;
  body: string;
}

export interface GuideChecklistItem {
  id: string;
  text: string;
  role: GuideRole;
}

export interface GuideParamRow {
  placeholder: string;
  meaning: string;
  where: string;
}

export interface GuideNetworkEgressRow {
  destination: string;
  usage: string;
  when: 'runtime' | 'deploy';
  env?: 'dev' | 'prod' | 'both';
}

export interface GuidePrerequisite {
  id: string;
  title: string;
  description: string;
  owner: GuideRole;
  /** Must be true before Terraform / deploy */
  blocking: boolean;
  /** Long lead time — request as early as possible */
  requestEarly?: boolean;
}

export interface GuideOverviewPillar {
  icon: 'subscription' | 'collector' | 'metrics';
  title: string;
  description: string;
}

export interface GuideBbResource {
  name: string;
  pattern: string;
  example: string;
  note: string;
  color: 'emerald' | 'blue' | 'amber' | 'violet' | 'slate';
}

export interface GuideFlowStep {
  step: string;
  title: string;
  who: GuideRole;
  detail: string;
}

/** Central DCM ECR — one AWS account per GitHub environment */
export const DCM_ECR_BY_ENV = {
  dev: {
    accountId: '551656632516',
    accountName: 'awss-wl-dcm',
    registry: '551656632516.dkr.ecr.eu-central-1.amazonaws.com',
    defaultRepo: 'awsd-dcm-azure-collector',
  },
  prod: {
    accountId: '884068385310',
    accountName: 'awsp-dcm',
    registry: '884068385310.dkr.ecr.eu-central-1.amazonaws.com',
    defaultRepo: 'awsp-dcm-azure-collector',
  },
} as const;

/** HTTPS egress from App Service integration subnet — request from LZ network team before deploy. */
export const GUIDE_NETWORK_EGRESS: GuideNetworkEgressRow[] = [
  {
    destination: 'login.microsoftonline.com',
    usage: 'Entra ID auth (collector SP + App Service MI)',
    when: 'runtime',
  },
  {
    destination: 'management.azure.com',
    usage: 'Azure APIs (ADF, Databricks, Cost, Security, …)',
    when: 'runtime',
  },
  {
    destination: 'dev.apixnp.alzp.tgscloud.net',
    usage: 'DCM ingestion via Apigee (dev/mutualized)',
    when: 'runtime',
    env: 'dev',
  },
  {
    destination: '551656632516.dkr.ecr.eu-central-1.amazonaws.com',
    usage: 'Pull collector image — ECR dev (awss-wl-dcm)',
    when: 'deploy',
    env: 'dev',
  },
  {
    destination: '884068385310.dkr.ecr.eu-central-1.amazonaws.com',
    usage: 'Pull collector image — ECR prod (awsp-dcm)',
    when: 'deploy',
    env: 'prod',
  },
  {
    destination: 'api.ecr.eu-central-1.amazonaws.com',
    usage: 'ECR GetAuthorizationToken',
    when: 'deploy',
    env: 'both',
  },
  {
    destination: 'prod-eu-central-1-starport-layer-bucket.s3.eu-central-1.amazonaws.com',
    usage: 'Docker image layers (ECR)',
    when: 'deploy',
    env: 'both',
  },
];

export const GUIDE_NETWORK_EGRESS_NOTES = [
  'Source: App Service DCM integration subnet (BB — e.g. azr{env}fn{appcode}-dcm, /28).',
  'Protocol: outbound HTTPS (443). Mechanism: NAT Gateway, Azure Firewall FQDN rules, or corporate proxy — per LZ design.',
  'ECR dev = AWS 551656632516 (awss-wl-dcm). ECR prod = AWS 884068385310 (awsp-dcm). Open the registry matching your LZ environment.',
  'No Azure ACR in client LZ — image lives on central DCM AWS ECR only.',
  'Full doc: docs/07-lz-onboarding/README.md',
];

export const LZ_ONBOARDING_STORAGE_KEY = 'dcm-lz-onboarding-checklist-v5-en';

/** Azure client LZ only — AWS ALZ uses a different collector + infra path. */
export const GUIDE_SCOPE = 'azure-lz' as const;

export const GUIDE_HERO = {
  eyebrow: 'New Azure Landing Zone',
  title: 'Connect your LZ to Data Connect Monitoring',
  subtitle:
    'This guide walks you through onboarding a new Azure IASP client landing zone. You deploy a small DCM stack inside your subscription, pull the collector image from central AWS ECR, and start sending metrics to DCM.',
  disclaimer:
    'Replace every placeholder with your own LZ values. DataSquad, novadatahub, and future LZs all follow the same model — client LZ in Azure, shared central ECR.',
};

export const GUIDE_OVERVIEW_INTRO = {
  title: 'How LZ onboarding works',
  description:
    'You deploy a small DCM stack inside your Azure subscription. A collector container (from central AWS ECR) reads your Azure resources and sends metrics to DCM Core. Terraform only creates the shell — the image and network paths are separate steps.',
};

export const GUIDE_PREREQUISITES: GuidePrerequisite[] = [
  {
    id: 'sub',
    title: 'Client Azure subscription',
    description:
      'IASP landing zone subscription — name, UUID, environment (d/m/p), and a contact email.',
    owner: 'you',
    blocking: true,
  },
  {
    id: 'vnet',
    title: 'VNet + Private Endpoint subnet',
    description:
      'LZ VNet must exist. PE subnet is pre-existing (Key Vault private link). BB creates the integration subnet (/28).',
    owner: 'devops',
    blocking: true,
  },
  {
    id: 'firewall',
    title: 'Outbound firewall rules (6 FQDNs)',
    description:
      'HTTPS egress from the App Service integration subnet to Entra, Azure Mgmt, Apigee, and AWS ECR. Often the longest lead time — open a ticket with the LZ network team on day 1.',
    owner: 'devops',
    blocking: true,
    requestEarly: true,
  },
  {
    id: 'bask',
    title: 'BASK satellite + Terraform access',
    description:
      'BA-{YOUR_LZ}-Infrastructure repo with DataintDCM/ClientInfra satellite and rights to apply the BB module.',
    owner: 'devops',
    blocking: true,
  },
  {
    id: 'gh-target',
    title: 'GitHub deploy target (Step 6)',
    description:
      'Entry in azure-collector-deploy-targets.json + Builder SP on your subscription — DCM team or PR in dataint-dcm-app.',
    owner: 'devops',
    blocking: false,
  },
  {
    id: 'entra',
    title: 'Entra admin (if needed)',
    description:
      'Collector Service Principal may need admin consent for API permissions — plan with identity team.',
    owner: 'you',
    blocking: false,
  },
];

export const GUIDE_OVERVIEW_PILLARS: GuideOverviewPillar[] = [
  {
    icon: 'subscription',
    title: 'Inside your subscription',
    description:
      'Terraform Building Block creates RG, Key Vault, App Service shell, subnets, and Managed Identity — all in the client Azure LZ.',
  },
  {
    icon: 'collector',
    title: 'Image from central ECR',
    description:
      'No registry in your LZ. GitHub CI pushes the Docker image to central AWS ECR (dev 551656632516 / prod 884068385310), then deploys it onto your App Service.',
  },
  {
    icon: 'metrics',
    title: 'Metrics to DCM Core',
    description:
      'The collector reads Azure (ADF, Databricks, cost, …) and sends HTTPS KPIs to Apigee → DCM backend → this app.',
  },
];

export const GUIDE_BB_RESOURCES: GuideBbResource[] = [
  {
    name: 'Resource Group',
    pattern: 'azr{env}rg{appcode}04-dcm',
    example: 'azrmrgndth04-dcm',
    note: 'Container for all DCM client resources',
    color: 'slate',
  },
  {
    name: 'Key Vault',
    pattern: 'azr{env}kv{appcode}-dcm',
    example: 'azrmkvndth-dcm',
    note: '4× dcm-* secrets + Private Endpoint on PE subnet',
    color: 'emerald',
  },
  {
    name: 'App Service',
    pattern: 'azr{env}fn{appcode}-dcm',
    example: 'azrmfnndth-dcm',
    note: 'Empty after Terraform — collector image installed in Step 6',
    color: 'blue',
  },
  {
    name: 'Storage Account',
    pattern: 'azr{env}st{appcode}-dcm',
    example: 'azrmstndth-dcm',
    note: 'App Service runtime storage',
    color: 'amber',
  },
  {
    name: 'Integration Subnet',
    pattern: '/28 CIDR (new)',
    example: '10.233.117.176/28',
    note: 'Created by BB — App Service VNet integration',
    color: 'violet',
  },
  {
    name: 'PE Subnet',
    pattern: 'pre-existing',
    example: 'subnet-d-ndth',
    note: 'Already in LZ VNet — Key Vault private link',
    color: 'violet',
  },
];

export const GUIDE_IMAGE_FLOW = {
  dev: DCM_ECR_BY_ENV.dev,
  prod: DCM_ECR_BY_ENV.prod,
  pushWorkflow: 'dcm-azure-collector.yml',
  deployWorkflow: 'dcm-azure-collector-deploy-lz.yml',
  pushSteps: [
    'Developer merges code in dataint-dcm-app',
    'CI builds Docker image from packages/dcm-azure-collector',
    'CI assumes IAM role on the ECR account for GitHub environment (dev or prod)',
    'Image pushed to ECR with tags :latest and :<git-sha>',
  ],
  pullSteps: [
    'deploy-lz.yml loads your LZ target from azure-collector-deploy-targets.json',
    'CI resolves ECR registry from github_environment (dev → 551656632516, prod → 884068385310)',
    'CI gets temporary ECR token (aws ecr get-login-password)',
    'az webapp config container set — image + AWS registry credentials',
    'App Service restarts and pulls image from ECR (public path, not via VNet)',
  ],
};

export const GUIDE_JOURNEY: GuideFlowStep[] = [
  {
    step: '1',
    title: 'Gather LZ details',
    who: 'you',
    detail: 'Subscription, env, collectors, contact email',
  },
  {
    step: '2',
    title: 'Start @dp-dcm-lz-client',
    who: 'you',
    detail: 'az login on YOUR client subscription',
  },
  {
    step: '3',
    title: 'Entra collector SP',
    who: 'agent',
    detail: 'Service Principal + Collector role',
  },
  {
    step: '4',
    title: 'Terraform (BB)',
    who: 'devops',
    detail: 'BASK satellite → empty App Service shell',
  },
  {
    step: '5',
    title: 'Secrets in KV',
    who: 'you',
    detail: 'dcm-entra-* + dcm-apigee-api-key in …-dcm vault',
  },
  {
    step: '6',
    title: 'Deploy collector image',
    who: 'devops',
    detail: 'ECR push + deploy-lz.yml → container on App Service',
  },
  { step: '7', title: 'Validate', who: 'agent', detail: 'Ingest test + metrics visible in DCM' },
];

/** Copilot message — replace every <…> with your values */
export const COPILOT_MESSAGE_TEMPLATE = `@dp-dcm-lz-client Azure : sub-iasp-lz-<LZ_NAME>, env=<d|m|p>, subscription_id=<SUBSCRIPTION_UUID>, <firstname.lastname>@totalenergies.com`;

export const COPILOT_PARAMS: GuideParamRow[] = [
  {
    placeholder: '<LZ_NAME>',
    meaning: 'Short LZ name (without sub-iasp-lz- prefix)',
    where: 'Azure Portal → Subscriptions → client subscription name',
  },
  {
    placeholder: '<d|m|p>',
    meaning: 'Environment: d = dev, m = mutualized, p = production',
    where: 'Your LZ / infra team convention',
  },
  {
    placeholder: '<SUBSCRIPTION_UUID>',
    meaning: 'Azure subscription ID of the client LZ',
    where: 'Azure Portal → Subscription → Properties → Subscription ID',
  },
  {
    placeholder: '<firstname.lastname>@totalenergies.com',
    meaning: 'Contact email for onboarding',
    where: 'Your identity or LZ owner',
  },
];

export const AZURE_LZ_ARCHITECTURE_NOTES = [
  'Everything in the diagram lives in the client Azure subscription — DCM Core is separate (central).',
  'Step 4 (Terraform): Building Block creates the host. Step 6 (CI): Docker image from central ECR.',
  'No ACR in client LZ — image pulled from central DCM AWS ECR (dev 551656632516 or prod 884068385310).',
  'VNet + PE subnet must exist before apply; integration subnet is created by the BB.',
  'Naming: azr + env (d/m/p) + resource type + app code + -dcm suffix.',
];

/** Azure LZ onboarding — simplified step order */
export const GUIDE_STEPS: GuidePhase[] = [
  {
    id: 's1',
    step: 'Step 1',
    role: 'you',
    title: 'Gather your LZ details',
    body: 'Client subscription name, subscription UUID, environment (d/m/p), contact email, and which collectors you need (ADF, Databricks, cost, databases, …). The agent derives source_lz_id — do not guess it.',
  },
  {
    id: 's2',
    step: 'Step 2',
    role: 'you',
    title: 'Start the Copilot agent',
    body: 'Install @dp-dcm-lz-client once, az login to the client LZ subscription you are onboarding, paste the message with YOUR placeholders filled in.',
  },
  {
    id: 's3',
    step: 'Step 3',
    role: 'agent',
    title: 'Entra identity for the collector',
    body: 'Agent creates AZR-IASP-LZ-{lzName}-dcm-collector and assigns Collector role on DCM back-ingestion SP. Entra admin may need to grant consent.',
  },
  {
    id: 's4',
    step: 'Step 4',
    role: 'devops',
    title: 'Deploy Azure infra (Building Block)',
    body: 'BASK satellite DataintDCM/ClientInfra in BA-{YOUR_LZ}-Infrastructure. Module azr-iac-bb-dataint-dcm creates RG, KV, empty App Service, storage, integration subnet. See architecture diagram.',
  },
  {
    id: 's5',
    step: 'Step 5',
    role: 'you',
    title: 'Store secrets in the DCM Key Vault',
    body: 'Four dcm-* secrets in the BB Key Vault (azr{env}kv{appcode}-dcm). Apigee key is shared per DCM environment — copy the value into your LZ vault.',
  },
  {
    id: 's6',
    step: 'Step 6',
    role: 'devops',
    title: 'Deploy collector Docker image (often missed)',
    body: 'App Service is empty after Terraform. Run dcm-azure-collector.yml (push ECR) then deploy-lz.yml with your deploy_target key and matching github_environment (dev/prod).',
  },
  {
    id: 's7',
    step: 'Step 7',
    role: 'agent',
    title: 'Validate end-to-end',
    body: 'Apigee ingest test (HTTP 202) + App Service logs show collection cycles without auth or image-pull errors.',
  },
];

export const GUIDE_CHECKLIST: GuideChecklistItem[] = [
  { id: 'c1', text: 'I have client subscription name + UUID', role: 'you' },
  { id: 'c2', text: 'Copilot agent installed + az login on the LZ I am onboarding', role: 'you' },
  { id: 'c3', text: '@dp-dcm-lz-client message sent with MY values (not another LZ)', role: 'you' },
  { id: 'c4', text: 'Collectors selected (ADF, Databricks, cost, databases, …)', role: 'you' },
  { id: 'c5', text: 'Azure LZ infra applied (BA-{LZ}-Infrastructure + BB)', role: 'devops' },
  {
    id: 'c5b',
    text: 'Firewall egress opened (Entra, Azure Mgmt, Apigee, ECR — 6 FQDNs)',
    role: 'devops',
  },
  { id: 'c6', text: 'Four dcm-* secrets in Key Vault …-dcm', role: 'you' },
  {
    id: 'c7',
    text: 'Collector image deployed via deploy-lz.yml (ECR → App Service)',
    role: 'devops',
  },
  { id: 'c8', text: 'Logs OK + metrics visible in DCM', role: 'agent' },
];

export const GUIDE_TROUBLESHOOT = [
  {
    symptom: 'Where does the collector run?',
    action: 'In your client Azure subscription (App Service azr*fn*-dcm) — not DCM Core',
  },
  {
    symptom: 'Apigee test OK but nothing in DCM',
    action: 'Step 6 not done — collector Docker image not on App Service',
  },
  { symptom: 'Apigee 403', action: 'Use header x-apif-apikey (not x-api-key)' },
  { symptom: 'Key Vault blocked', action: 'PIM + whitelist your IP on KV firewall' },
  {
    symptom: 'App Service cannot pull Docker image',
    action:
      'Open ECR/S3 egress for your env (dev 551656632516… or prod 884068385310…) — then re-run deploy-lz.yml',
  },
  {
    symptom: 'ImagePullFailure / token expired',
    action: 'ECR registry password lasts ~12h — re-run dcm-azure-collector-deploy-lz.yml',
  },
  {
    symptom: 'Collector auth errors at startup',
    action: 'Open login.microsoftonline.com from App Service subnet (often blocked first)',
  },
  {
    symptom: 'Deploy denied from my laptop',
    action: 'Expected — use GitHub CI with your LZ Builder SP',
  },
] as const;

export const ROLE_LABELS: Record<GuideRole, string> = {
  you: 'LZ team',
  agent: 'AI agent',
  devops: 'DevOps',
};

export const BB_INSTALL_DOC_URL =
  'https://github.com/TotalEnergiesCode/azr-iac-bb-dataint-dcm/blob/main/installation.md';

export const LZ_ONBOARDING_DOC_URL =
  'https://github.com/TotalEnergiesCode/dataint-dcm-app/blob/develop/docs/07-lz-onboarding/README.md';
