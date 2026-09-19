<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Check,
  Delete,
  Edit,
  FolderOpened,
  MoreFilled,
  Moon,
  Refresh,
  Setting,
  Sunny,
  SwitchButton,
  Upload,
} from '@element-plus/icons-vue'
import { decodeTaskEvent, native } from '@/services/native'
import { useAppStore } from '@/stores/app'
import type { Account, AppSettings, AppState, RateLimit, RateLimitWindow, TaskEvent } from '@/types'

const store = useAppStore()
const settingsVisible = ref(false)
const renameVisible = ref(false)
const renameAccount = ref<Account | null>(null)
const renameValue = ref('')
const settingsDraft = reactive<AppSettings>({ ...store.settings })
const now = ref(Date.now())
let timer: number | undefined

const hasAccounts = computed(() => store.accountCount > 0)
const busy = computed(() => store.activeTasks.size > 0)

const statusText: Record<string, string> = {
  idle: '等待刷新',
  loading: '刷新中',
  ready: '正常',
  auth_error: '认证失效',
  network_error: '网络错误',
  codex_unavailable: 'Codex 不可用',
  error: '未知错误',
}

function applyTheme(): void {
  const preferred = store.settings.theme === 'system'
    ? window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    : store.settings.theme
  document.documentElement.dataset.theme = preferred
}

function formatDuration(minutes: number): string {
  if (!minutes) return '额度'
  if (minutes % 10080 === 0) return `${minutes / 10080} 周额度`
  if (minutes % 1440 === 0) return `${minutes / 1440} 天额度`
  if (minutes % 60 === 0) return `${minutes / 60} 小时额度`
  return `${minutes} 分钟额度`
}

function limitName(limit: RateLimit): string {
  return limit.limitName || formatDuration(limit.primary.windowDurationMins)
}

function remainingColor(window: RateLimitWindow): string {
  if (window.remainingPercent <= 0) return 'danger'
  if (window.remainingPercent < 20) return 'danger'
  if (window.remainingPercent <= 50) return 'warning'
  return 'success'
}

function formatReset(resetAt?: number | null): string {
  if (!resetAt) return '刷新时间未知'
  const date = new Date(resetAt * 1000)
  return date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function formatCountdown(resetAt?: number | null): string {
  if (!resetAt) return '等待服务器返回刷新时间'
  const seconds = Math.max(0, resetAt - Math.floor(now.value / 1000))
  if (!seconds) return '即将刷新'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  if (days) return `${days}天${hours}小时后刷新`
  if (hours) return `${hours}小时${minutes}分钟后刷新`
  return `${Math.max(1, minutes)}分钟后刷新`
}

function lastRefresh(account: Account): string {
  if (!account.lastRefreshAt) return '尚未刷新'
  return new Date(account.lastRefreshAt * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

async function refreshAll(): Promise<void> {
  const result = await native.refreshAll()
  if (result.accepted === false) ElMessage.error(String(result.error ?? '刷新失败'))
  await store.load(false)
}

async function refreshOne(account: Account): Promise<void> {
  const result = await native.refreshAccount(account.id)
  if (result.accepted === false) ElMessage.error(String(result.error ?? '刷新失败'))
  await store.load(false)
}

async function importAccount(): Promise<void> {
  const result = await native.importCurrentAccount()
  if (result.accepted === false) {
    ElMessage.error(String(result.error ?? '导入失败'))
    return
  }
  await store.load(false)
  const detail = (result.result ?? {}) as { accountId?: string; suggestSwitch?: boolean }
  const account = store.accounts.find((item) => item.id === detail.accountId)
  if (account && detail.suggestSwitch) {
    try {
      await ElMessageBox.confirm(
        `账号已导入为「${account.name}」。是否立即将 CODEX_HOME 切换到受管目录？`,
        '导入完成',
        { confirmButtonText: '切换到受管目录', cancelButtonText: '稍后再说' },
      )
      await switchAccount(account)
    } catch {
      // 用户选择稍后切换。
    }
  }
}

async function switchAccount(account: Account, closeCodex = false): Promise<void> {
  const result = await native.switchAccount(account.id, closeCodex)
  if (result.accepted === false) {
    ElMessage.error(String(result.error ?? '切换失败'))
    return
  }
  const detail = (result.result ?? {}) as { code?: string; success?: boolean; accountId?: string }
  if (detail.code === 'codex_running' && !closeCodex) {
    if (store.settings.autoCloseCodex) {
      await switchAccount(account, true)
      return
    }
    try {
      await ElMessageBox.confirm(
        'Codex 当前正在运行。切换账号需要先关闭 Codex，否则当前进程会继续使用旧的 CODEX_HOME。',
        'Codex 正在运行',
        { type: 'warning', confirmButtonText: '关闭 Codex 并切换', cancelButtonText: '取消' },
      )
      await switchAccount(account, true)
    } catch {
      // 用户取消切换。
    }
    return
  }
  await store.load(false)
  if (detail.success) {
    ElMessage.success(`已切换到：${account.name}`)
    if (store.settings.autoStartCodex) await native.startCodex(account.id)
  }
}

async function confirmRemove(account: Account): Promise<void> {
  if (account.current) return
  try {
    await ElMessageBox.confirm(
      `这将删除 Codex Account Manager 保存的完整 CODEX_HOME：\n${account.home}\n\n其中可能包含登录凭据、历史、Sessions 和配置。此操作无法撤销。`,
      `删除「${account.name}」？`,
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
  const result = await native.removeAccount(account.id)
    if (result.accepted === false) ElMessage.error(String(result.error ?? '删除失败'))
    else await store.load(false)
  } catch {
    // 用户取消确认框不需要额外提示。
  }
}

function showRename(account: Account): void {
  renameAccount.value = account
  renameValue.value = account.name
  renameVisible.value = true
}

async function saveRename(): Promise<void> {
  if (!renameAccount.value) return
  const result = await native.renameAccount(renameAccount.value.id, renameValue.value)
  if (result.accepted === false) {
    ElMessage.error(String(result.error ?? '修改名称失败'))
    return
  }
  renameVisible.value = false
  await store.load(false)
  ElMessage.success('名称已更新')
}

async function copyHome(account: Account): Promise<void> {
  await navigator.clipboard?.writeText(account.home)
  ElMessage.success('CODEX_HOME 路径已复制')
}

async function openSettings(): Promise<void> {
  Object.assign(settingsDraft, store.settings)
  settingsVisible.value = true
  await nextTick()
}

async function saveSettings(): Promise<void> {
  await store.saveSettings({ ...settingsDraft })
  settingsVisible.value = false
  applyTheme()
  ElMessage.success('设置已保存')
}

async function handleTask(event: TaskEvent): Promise<void> {
  store.handleTask(event)
  if (event.event !== 'completed') {
    if (event.event === 'failed') ElMessage.error(event.error ?? '后台任务失败')
    return
  }
  const result = event.result ?? {}
  if (event.taskType === 'switch' && result.code === 'codex_running') {
    const account = store.accounts.find((item) => item.id === result.accountId)
    if (!account) return
    if (store.settings.autoCloseCodex) {
      await switchAccount(account, true)
      return
    }
    try {
      await ElMessageBox.confirm(
        'Codex 当前正在运行。切换账号需要先关闭 Codex，否则当前进程会继续使用旧的 CODEX_HOME。',
        'Codex 正在运行',
        { type: 'warning', confirmButtonText: '关闭 Codex 并切换', cancelButtonText: '取消' },
      )
      await switchAccount(account, true)
    } catch {
      // 用户取消切换。
    }
  } else if (event.taskType === 'switch' && result.success) {
    ElMessage.success(`已切换到：${store.accounts.find((item) => item.id === result.accountId)?.name ?? '目标账号'}`)
    if (store.settings.autoStartCodex) await native.startCodex(String(result.accountId))
  } else if (event.taskType === 'import' && result.accountId) {
    const account = store.accounts.find((item) => item.id === result.accountId)
    if (account && result.suggestSwitch) {
      try {
        await ElMessageBox.confirm(
          `账号已导入为「${account.name}」。是否立即将 CODEX_HOME 切换到受管目录？`,
          '导入完成',
          { confirmButtonText: '切换到受管目录', cancelButtonText: '稍后再说' },
        )
        await switchAccount(account)
      } catch {
        // 用户选择稍后切换。
      }
    }
  }
}

function handleState(payload: string): void {
  try {
    store.applyState(JSON.parse(payload) as AppState)
  } catch {
    ElMessage.error('后端状态解析失败')
  }
}

function handleNotification(payload: string): void {
  try {
    const value = JSON.parse(payload) as { type?: string; message?: string }
    if (value.message) ElMessage[value.type === 'error' ? 'error' : 'info'](value.message)
  } catch {
    // 忽略无法解析的通知。
  }
}

watch(() => store.settings.theme, applyTheme)
watch(() => store.settings, applyTheme, { deep: true })

onMounted(async () => {
  native.on('stateChanged', handleState)
  native.on('accountsChanged', handleState)
  native.on('taskEvent', (payload) => {
    const event = decodeTaskEvent(payload)
    if (event) void handleTask(event)
  })
  native.on('notification', handleNotification)
  await store.load()
  applyTheme()
  timer = window.setInterval(() => {
    now.value = Date.now()
    void store.load(false)
  }, 2000)
})

onUnmounted(() => {
  if (timer) window.clearInterval(timer)
})
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <div class="brand-block">
        <div class="brand-mark"><span></span><span></span><span></span></div>
        <div>
          <div class="eyebrow">LOCAL ACCOUNT WORKSPACE</div>
          <h1>Codex Account Manager</h1>
        </div>
      </div>
      <div class="top-actions">
        <el-button class="icon-button" text circle title="设置" @click="openSettings">
          <el-icon><Setting /></el-icon>
        </el-button>
        <el-button class="theme-button" text circle title="切换主题" @click="store.saveSettings({ theme: store.settings.theme === 'dark' ? 'light' : 'dark' })">
          <el-icon><Sunny v-if="store.settings.theme !== 'dark'" /><Moon v-else /></el-icon>
        </el-button>
        <el-button class="ghost-button" :loading="busy" @click="refreshAll">
          <el-icon><Refresh /></el-icon>刷新全部
        </el-button>
        <el-button class="primary-button" @click="importAccount">
          <el-icon><Upload /></el-icon>添加当前账号
        </el-button>
      </div>
    </header>

    <main class="content">
      <section class="intro-row">
        <div>
          <div class="section-kicker">ACCOUNTS</div>
          <h2>你的 Codex 账号</h2>
          <p>每个账号拥有独立的 CODEX_HOME，工作区和代码项目保持不变。</p>
        </div>
        <div class="account-summary">
          <span class="summary-dot"></span>
          <strong>{{ store.accountCount }}</strong>
          <span>个账号</span>
        </div>
      </section>

      <el-alert v-if="store.systemMessage" :title="store.systemMessage" type="warning" show-icon closable />

      <div v-if="store.loading" class="cards-grid">
        <el-card v-for="item in 2" :key="item" class="account-card skeleton-card" shadow="never">
          <el-skeleton :rows="7" animated />
        </el-card>
      </div>

      <div v-else-if="!hasAccounts" class="empty-state">
        <div class="empty-icon"><SwitchButton /></div>
        <h3>还没有受管账号</h3>
        <p>从当前 Codex Home 导入第一个账号，之后就可以一键切换和查看额度。</p>
        <el-button class="primary-button" @click="importAccount"><Upload />添加当前 Codex 账号</el-button>
        <small>导入会复制一次 CODEX_HOME，并在保存前进行二次账号验证。</small>
      </div>

      <div v-else class="cards-grid">
        <el-card v-for="account in store.accounts" :key="account.id" class="account-card" shadow="never">
          <div class="card-header">
            <div class="account-title">
              <span class="status-orb" :class="account.status"></span>
              <div>
                <div class="name-line">
                  <h3>{{ account.name }}</h3>
                  <el-tag v-if="account.current" class="current-tag" effect="plain" size="small">CURRENT</el-tag>
                </div>
                <div class="email">{{ account.email }}</div>
              </div>
            </div>
            <el-dropdown trigger="click">
              <el-button class="more-button" text circle><el-icon><MoreFilled /></el-icon></el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-if="!account.current" @click="switchAccount(account)">切换到此账号</el-dropdown-item>
                  <el-dropdown-item @click="refreshOne(account)">刷新额度</el-dropdown-item>
                  <el-dropdown-item @click="showRename(account)">修改名称</el-dropdown-item>
                  <el-dropdown-item @click="native.openAccountHome(account.id)">打开 CODEX_HOME</el-dropdown-item>
                  <el-dropdown-item @click="copyHome(account)">复制 CODEX_HOME 路径</el-dropdown-item>
                  <el-dropdown-item divided :disabled="account.current" @click="confirmRemove(account)">删除账号</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <div class="plan-row">
            <span>{{ account.planType || 'ChatGPT Plus' }}</span>
            <el-tag :type="account.status === 'ready' ? 'success' : account.status === 'loading' ? 'info' : 'danger'" effect="plain" size="small">
              {{ statusText[account.status] || '未知状态' }}
            </el-tag>
          </div>

          <div v-if="account.rateLimits.length" class="limits-list">
            <div v-for="limit in account.rateLimits" :key="limit.limitId" class="limit-block">
              <div class="limit-heading"><span>{{ limitName(limit) }}</span><strong>剩余 {{ Math.round(limit.primary.remainingPercent) }}%</strong></div>
              <el-progress :percentage="limit.primary.remainingPercent" :status="remainingColor(limit.primary)" :show-text="false" :stroke-width="8" />
              <div class="limit-meta"><span>{{ formatReset(limit.primary.resetsAt) }}</span><span>{{ formatCountdown(limit.primary.resetsAt) }}</span></div>
              <template v-if="limit.secondary">
                <div class="limit-heading secondary-heading"><span>次级 · {{ formatDuration(limit.secondary.windowDurationMins) }}</span><strong>剩余 {{ Math.round(limit.secondary.remainingPercent) }}%</strong></div>
                <el-progress :percentage="limit.secondary.remainingPercent" :status="remainingColor(limit.secondary)" :show-text="false" :stroke-width="8" />
                <div class="limit-meta"><span>{{ formatReset(limit.secondary.resetsAt) }}</span><span>{{ formatCountdown(limit.secondary.resetsAt) }}</span></div>
              </template>
            </div>
          </div>
          <div v-else class="no-limits">暂无额度缓存，点击刷新获取最新数据</div>

          <div v-if="account.errorMessage" class="error-note">{{ account.errorMessage }}</div>
          <div class="card-footer">
            <span>最近刷新 {{ lastRefresh(account) }}</span>
            <div class="footer-actions">
              <el-button text class="small-action" :loading="account.status === 'loading'" @click="refreshOne(account)"><Refresh />刷新</el-button>
              <el-button v-if="!account.current" class="switch-button" @click="switchAccount(account)">切换到此账号</el-button>
              <el-tag v-else class="active-label" effect="plain"><Check />正在使用</el-tag>
            </div>
          </div>
        </el-card>
      </div>

      <footer class="bottom-note">
        <span><Check /> 所有凭据都保存在本机，不会上传到第三方服务器。</span>
        <el-button text @click="native.openLogs"><FolderOpened />打开日志</el-button>
      </footer>
    </main>

    <el-dialog v-model="renameVisible" title="修改账号名称" width="360px">
      <el-input v-model="renameValue" maxlength="80" show-word-limit @keyup.enter="saveRename" />
      <template #footer><el-button @click="renameVisible = false">取消</el-button><el-button type="primary" @click="saveRename">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="settingsVisible" title="设置" width="480px" class="settings-dialog">
      <div class="settings-section">
        <div class="settings-label"><strong>外观</strong><span>选择界面主题</span></div>
        <el-radio-group v-model="settingsDraft.theme" size="small"><el-radio-button label="system">跟随系统</el-radio-button><el-radio-button label="light">浅色</el-radio-button><el-radio-button label="dark">深色</el-radio-button></el-radio-group>
      </div>
      <div class="settings-section">
        <div class="settings-label"><strong>额度自动刷新</strong><span>在后台定时读取各账号额度</span></div>
        <div class="setting-controls"><el-switch v-model="settingsDraft.autoRefresh" /><el-select v-model="settingsDraft.refreshIntervalMinutes" :disabled="!settingsDraft.autoRefresh" size="small" style="width: 110px"><el-option v-for="minute in [1, 3, 5, 10]" :key="minute" :label="`${minute} 分钟`" :value="minute" /></el-select></div>
      </div>
      <div class="settings-section"><div class="settings-label"><strong>切换账号时自动关闭 Codex</strong><span>切换前自动结束 Codex 进程</span></div><el-switch v-model="settingsDraft.autoCloseCodex" /></div>
      <div class="settings-section"><div class="settings-label"><strong>切换成功后启动 Codex</strong><span>使用目标账号的 CODEX_HOME 启动</span></div><el-switch v-model="settingsDraft.autoStartCodex" /></div>
      <div class="settings-section"><div class="settings-label"><strong>关闭窗口时最小化到托盘</strong><span>通过托盘菜单退出应用</span></div><el-switch v-model="settingsDraft.closeToTray" /></div>
      <div class="settings-section"><div class="settings-label"><strong>开机启动</strong><span>仅写入当前用户注册表，无需管理员权限</span></div><el-switch v-model="settingsDraft.startWithWindows" /></div>
      <div class="settings-section"><div class="settings-label"><strong>系统通知</strong><span>显示导入、切换和刷新结果</span></div><el-switch v-model="settingsDraft.showNotifications" /></div>
      <template #footer><el-button @click="settingsVisible = false">取消</el-button><el-button type="primary" @click="saveSettings">保存设置</el-button></template>
    </el-dialog>
  </div>
</template>
