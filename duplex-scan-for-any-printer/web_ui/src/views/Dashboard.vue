<template src="./Dashboard.html"></template>
<style scoped src="./Dashboard.css"></style>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useScansStore } from '@/stores/scans'

const STATUS_REFRESH_INTERVAL = 3_000

const scansStore = useScansStore()
const statusTimer = ref<ReturnType<typeof setInterval> | null>(null)

// ── Bot settings modal ──────────────────────────────────────────────────────
const showBotSettings = ref(false)
const copyToast = ref('')

const registeredChatEntries = computed(() =>
  Object.entries(scansStore.botInfo?.registered_chats ?? {})
)

function openBotSettings() {
  showBotSettings.value = true
  scansStore.fetchBotInfo()
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    showToast(`Copied: ${text}`)
  } catch {
    showToast('Copy failed')
  }
}

async function copyYamlSnippet() {
  const ids = scansStore.botInfo?.registered_chats
    ? Object.values(scansStore.botInfo.registered_chats)
    : []
  const snippet =
    ids.length
      ? `telegram:\n  notify_chat_ids:\n${ids.map(id => `    - "${id}"`).join('\n')}`
      : `telegram:\n  notify_chat_ids:\n    - "YOUR_CHAT_ID"`
  await copyText(snippet)
}

function showToast(msg: string) {
  copyToast.value = msg
  setTimeout(() => (copyToast.value = ''), 2500)
}

// ── Session confirm / reject ────────────────────────────────────────────────
const actionLoading = ref(false)
const actionFeedback = ref<{ ok: boolean; message: string } | null>(null)

async function confirmSession(printRequested: boolean) {
  actionLoading.value = true
  actionFeedback.value = null
  const result = await scansStore.confirmSession(printRequested)
  actionLoading.value = false
  actionFeedback.value = {
    ok: result.ok,
    message: result.ok ? 'Session confirmed ✅' : `Error: ${result.message ?? 'unknown'}`,
  }
  setTimeout(() => (actionFeedback.value = null), 4000)
}

async function rejectSession() {
  actionLoading.value = true
  actionFeedback.value = null
  const result = await scansStore.rejectSession()
  actionLoading.value = false
  actionFeedback.value = {
    ok: result.ok,
    message: result.ok ? 'Session rejected ❌' : `Error: ${result.message ?? 'unknown'}`,
  }
  setTimeout(() => (actionFeedback.value = null), 4000)
}

// ── Status indicators ───────────────────────────────────────────────────────
const botStatusClass = computed(() => {
  if (!scansStore.botStatus) return 'disconnected'
  return scansStore.botStatus.connected ? 'connected' : 'disconnected'
})
const botStatusText = computed(() => {
  if (!scansStore.botStatus) return 'Unknown'
  return scansStore.botStatus.connected ? 'Connected' : 'Disconnected'
})

const sessionStatusClass = computed(() => {
  const state = scansStore.sessionStatus?.state
  if (state === 'WAIT_CONFIRM') return 'waiting'
  if (state === 'CONFIRMED' || state === 'REJECTED') return 'connected'
  return 'disconnected'
})
const sessionStatusText = computed(() => {
  const state = scansStore.sessionStatus?.state
  if (state === 'WAIT_CONFIRM') return 'Waiting'
  if (state === 'CONFIRMED') return 'Confirmed'
  if (state === 'REJECTED') return 'Rejected'
  return 'Idle'
})

// ── Refresh ─────────────────────────────────────────────────────────────────
function refreshAll() {
  scansStore.fetchBotStatus()
  scansStore.fetchSessionStatus()
  scansStore.fetchScans()
}

onMounted(() => {
  refreshAll()
  statusTimer.value = setInterval(refreshAll, STATUS_REFRESH_INTERVAL)
})
onBeforeUnmount(() => {
  if (statusTimer.value) clearInterval(statusTimer.value)
})
</script>
