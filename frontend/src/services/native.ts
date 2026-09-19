import type { AppState, AppSettings, TaskEvent } from '@/types'

type NativeSignal = { connect: (callback: (value: string) => void) => void }
type NativeObject = {
  [key: string]: ((...args: unknown[]) => void) | NativeSignal
}

const mockState: AppState = {
  currentAccount: null,
  accounts: [],
  settings: {
    theme: 'system',
    autoRefresh: true,
    refreshIntervalMinutes: 3,
    startWithWindows: false,
    minimizeToTray: true,
    closeToTray: true,
    autoCloseCodex: false,
    autoStartCodex: false,
    showNotifications: true,
  },
}

let bridge: NativeObject | null = null
const listeners = new Map<string, Array<(payload: string) => void>>()

function parseResult(value: string | undefined): Record<string, unknown> {
  if (!value) return {}
  try {
    return JSON.parse(value) as Record<string, unknown>
  } catch {
    return { accepted: false, error: value }
  }
}

function getMockResult(method: string, args: unknown[]): string {
  if (method === 'getAppState') return JSON.stringify(mockState)
  if (method === 'getAccounts') return JSON.stringify(mockState.accounts)
  if (method === 'getSettings') return JSON.stringify(mockState.settings)
  if (method === 'updateSettings') {
    Object.assign(mockState.settings, JSON.parse(String(args[0])))
    return JSON.stringify({ accepted: true, settings: mockState.settings })
  }
  return JSON.stringify({ accepted: false, error: '浏览器预览模式不支持该操作' })
}

export const native = {
  async connect(): Promise<void> {
    if (bridge) return
    if (window.qt?.webChannelTransport && window.QWebChannel) {
      await new Promise<void>((resolve) => {
        new window.QWebChannel!(window.qt!.webChannelTransport, (channel) => {
          bridge = channel.objects.appBridge as NativeObject
          for (const [name, callbacks] of listeners) {
            const signal = bridge[name] as NativeSignal | undefined
            signal?.connect((value) => callbacks.forEach((callback) => callback(value)))
          }
          resolve()
        })
      })
    } else {
      bridge = {}
    }
  },

  async call<T = Record<string, unknown>>(method: string, ...args: unknown[]): Promise<T> {
    await this.connect()
    const target = bridge?.[method]
    if (typeof target !== 'function') return parseResult(getMockResult(method, args)) as T
    return new Promise<T>((resolve) => {
      target(...args, (value: string) => resolve(parseResult(value) as T))
    })
  },

  on(signal: 'stateChanged' | 'accountsChanged' | 'taskEvent' | 'notification', callback: (payload: string) => void): void {
    const callbacks = listeners.get(signal) ?? []
    callbacks.push(callback)
    listeners.set(signal, callbacks)
    if (bridge?.[signal] && typeof bridge[signal] !== 'function') {
      ;(bridge[signal] as NativeSignal).connect(callback)
    }
  },

  async getAppState(): Promise<AppState> {
    return this.call<AppState>('getAppState')
  },
  async getAccounts(): Promise<AppState['accounts']> {
    return this.call<AppState['accounts']>('getAccounts')
  },
  async importCurrentAccount(): Promise<Record<string, unknown>> {
    return this.call('importCurrentAccount')
  },
  async switchAccount(id: string, closeCodex = false): Promise<Record<string, unknown>> {
    return this.call('switchAccount', id, closeCodex)
  },
  async refreshAccount(id: string): Promise<Record<string, unknown>> {
    return this.call('refreshAccount', id)
  },
  async refreshAll(): Promise<Record<string, unknown>> {
    return this.call('refreshAllAccounts')
  },
  async renameAccount(id: string, name: string): Promise<Record<string, unknown>> {
    return this.call('renameAccount', id, name)
  },
  async removeAccount(id: string): Promise<Record<string, unknown>> {
    return this.call('removeAccount', id)
  },
  async openAccountHome(id: string): Promise<Record<string, unknown>> {
    return this.call('openAccountHome', id)
  },
  async openLogs(): Promise<Record<string, unknown>> {
    return this.call('openLogs')
  },
  async getSettings(): Promise<AppSettings> {
    return this.call<AppSettings>('getSettings')
  },
  async saveSettings(settings: Partial<AppSettings>): Promise<Record<string, unknown>> {
    return this.call('updateSettings', JSON.stringify(settings))
  },
  async startCodex(id?: string): Promise<Record<string, unknown>> {
    return this.call('startCodex', id ?? '')
  },
  async quitApplication(): Promise<Record<string, unknown>> {
    return this.call('quitApplication')
  },
}

export function decodeTaskEvent(payload: string): TaskEvent | null {
  try {
    return JSON.parse(payload) as TaskEvent
  } catch {
    return null
  }
}
