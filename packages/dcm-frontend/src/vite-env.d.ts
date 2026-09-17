/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string
  readonly VITE_AZURE_TENANT_ID: string
  readonly VITE_AZURE_CLIENT_ID: string
  readonly VITE_AZURE_SCOPE: string
  readonly VITE_REDIRECT_URI: string
  readonly VITE_ENABLE_AUTH: string
  readonly VITE_DCM_DEV_ROLE?: string
  readonly VITE_DCM_DEV_USER_ID?: string
  readonly VITE_DCM_DEV_ENTRA_OID?: string
  readonly VITE_DCM_DEV_EMAIL?: string
  readonly VITE_DCM_DEV_DISPLAY_NAME?: string
  readonly VITE_DCM_DEV_LZ_IDS?: string
  readonly MODE: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
