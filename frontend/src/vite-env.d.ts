/// <reference types="vite/client" />

declare interface QtWebChannelBridge {
  [key: string]: (...args: unknown[]) => unknown
}

declare interface Window {
  qt?: { webChannelTransport: unknown }
  QWebChannel?: new (transport: unknown, callback: (channel: { objects: Record<string, QtWebChannelBridge> }) => void) => unknown
}
