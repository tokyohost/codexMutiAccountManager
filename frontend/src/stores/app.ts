import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { native } from '@/services/native'
import type { Account, AppSettings, AppState, TaskEvent } from '@/types'

export const useAppStore = defineStore('app', () => {
  const accounts = ref<Account[]>([])
  const settings = ref<AppSettings>({
    theme: 'system',
    autoRefresh: true,
    refreshIntervalMinutes: 3,
    startWithWindows: false,
    minimizeToTray: true,
    closeToTray: true,
    autoCloseCodex: false,
    autoStartCodex: false,
    showNotifications: true,
  })
  const currentAccount = ref<string | null>(null)
  const loading = ref(true)
  const activeTasks = ref(new Set<string>())
  const systemMessage = ref<string | null>(null)
  const accountCount = computed(() => accounts.value.length)

  function applyState(state: AppState): void {
    accounts.value = state.accounts ?? []
    currentAccount.value = state.currentAccount ?? null
    settings.value = { ...settings.value, ...(state.settings ?? {}) }
    systemMessage.value = state.configLoadError ?? null
    loading.value = false
  }

  async function load(): Promise<void> {
    loading.value = true
    applyState(await native.getAppState())
  }

  function handleTask(event: TaskEvent): void {
    if (event.event === 'started') activeTasks.value.add(event.taskId)
    if (event.event === 'completed' || event.event === 'failed') activeTasks.value.delete(event.taskId)
  }

  async function saveSettings(value: Partial<AppSettings>): Promise<void> {
    const result = await native.saveSettings(value)
    if (result.settings) settings.value = result.settings as AppSettings
  }

  return {
    accounts,
    settings,
    currentAccount,
    loading,
    activeTasks,
    systemMessage,
    accountCount,
    applyState,
    load,
    handleTask,
    saveSettings,
  }
})
