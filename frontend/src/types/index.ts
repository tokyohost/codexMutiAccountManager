export type AccountStatus =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'auth_error'
  | 'network_error'
  | 'codex_unavailable'
  | 'error'

export interface RateLimitWindow {
  usedPercent: number
  remainingPercent: number
  windowDurationMins: number
  resetsAt?: number | null
}

export interface RateLimit {
  limitId: string
  limitName: string
  primary: RateLimitWindow
  secondary?: RateLimitWindow | null
  rateLimitReachedType?: string | null
}

export interface Account {
  id: string
  name: string
  email: string
  planType?: string
  type?: string
  home: string
  authPath?: string
  current: boolean
  status: AccountStatus
  errorMessage?: string | null
  rateLimits: RateLimit[]
  lastRefreshAt?: number | null
  lastRefreshResult?: string | null
}

export interface AppSettings {
  theme: 'light' | 'dark' | 'system'
  autoRefresh: boolean
  refreshIntervalMinutes: number
  startWithWindows: boolean
  minimizeToTray: boolean
  closeToTray: boolean
  autoCloseCodex: boolean
  autoStartCodex: boolean
  showNotifications: boolean
}

export interface AppState {
  currentAccount: string | null
  accounts: Account[]
  settings: AppSettings
  configLoadError?: string | null
}

export interface TaskEvent {
  event: 'started' | 'progress' | 'completed' | 'failed'
  taskId: string
  taskType: string
  result?: Record<string, unknown>
  error?: string
  traceback?: string
}
