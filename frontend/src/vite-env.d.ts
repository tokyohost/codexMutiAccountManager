/// <reference types="vite/client" />

declare interface QtWebChannelBridge {
  [key: string]: (...args: unknown[]) => unknown
}

declare interface Window {
  pywebview?: { api: Record<string, (...args: unknown[]) => Promise<unknown>> }
  qt?: { webChannelTransport: unknown }
  QWebChannel?: new (transport: unknown, callback: (channel: { objects: Record<string, QtWebChannelBridge> }) => void) => unknown
}
