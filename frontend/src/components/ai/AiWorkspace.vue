<template>
  <section class="ai-workspace" data-workspace="ai" aria-label="AI 智能助手">
    <header class="ai-workspace__header">
      <div class="ai-workspace__title"><span>经营案台</span><strong>AI 智能助手</strong></div>
      <ul class="ai-workspace__facts" aria-label="服务状态">
        <li>只读问答</li><li>权限内数据</li><li>点击后跳转</li>
      </ul>
      <el-button class="ai-workspace__drawer-button" aria-label="打开会话索引" @click="drawerOpen = true">会话</el-button>
    </header>

    <div v-if="store.initializing" class="ai-workspace__state" aria-live="polite"><el-skeleton :rows="5" animated /></div>
    <div v-else-if="store.initialError" class="ai-workspace__state">
      <el-alert title="会话加载失败，请检查网络后重试。" type="error" :closable="false" show-icon />
      <el-button type="primary" @click="initialize">重新加载</el-button>
    </div>
    <div v-else class="ai-workspace__body">
      <ConversationSidebar
        class="ai-workspace__desktop-sidebar"
        :conversations="store.conversations"
        :active-id="store.activeConversationId"
        :generating="store.generatingByConversation"
        @create="createConversation"
        @select="openConversation"
        @rename="renameConversation"
        @delete="deleteConversation"
      />
      <main class="ai-workspace__conversation" aria-label="当前会话">
        <MessageList
          :conversation-id="store.activeConversationId"
          :messages="store.activeMessages"
          :suggestions="store.suggestions"
          :error="activeError"
          :scroll-position="activeScrollPosition"
          @save-scroll="store.saveScrollPosition"
          @suggestion="sendPrompt"
        />
        <div v-if="displayedSubmissionError && retryContent" class="ai-workspace__submission-error" role="alert">
          <span>{{ displayedSubmissionError }}</span>
          <el-button class="ai-workspace__retry" type="danger" plain :disabled="submitting || isGenerating" aria-label="重试发送" @click="retryPending">重试</el-button>
        </div>
        <MessageComposer :generating="isGenerating" :submitting="submitting" @submit="sendPrompt" @stop="stopGeneration" />
      </main>
    </div>
    <el-drawer v-model="drawerOpen" direction="ltr" size="min(86vw, 300px)" :with-header="false" class="ai-workspace__drawer">
      <ConversationSidebar
        :conversations="store.conversations"
        :active-id="store.activeConversationId"
        :generating="store.generatingByConversation"
        @create="createConversation"
        @select="openFromDrawer"
        @rename="renameConversation"
        @delete="deleteConversation"
      />
    </el-drawer>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useAiAssistantStore } from '@/store/aiAssistant'
import ConversationSidebar from './ConversationSidebar.vue'
import MessageComposer from './MessageComposer.vue'
import MessageList from './MessageList.vue'

const store = useAiAssistantStore()
const drawerOpen = ref(false)
const submitting = ref(false)
const pendingSubmission = ref(null)
const submissionFailure = ref(null)
const activeError = computed(() => store.errorByConversation[store.activeConversationId] || null)
const isGenerating = computed(() => Boolean(store.generatingByConversation[store.activeConversationId]))
const activeScrollPosition = computed(() => store.activeConversationId == null ? 0 : store.getScrollPosition(store.activeConversationId))
const retryContent = computed(() => {
  if (pendingSubmission.value?.conversationId == null || pendingSubmission.value?.conversationId === store.activeConversationId) {
    return pendingSubmission.value?.content || ''
  }
  if (!activeError.value) return ''
  return [...store.activeMessages].reverse().find((message) => message.role === 'user')?.content || ''
})
const displayedSubmissionError = computed(() => {
  if (submissionFailure.value?.conversationId == null || submissionFailure.value?.conversationId === store.activeConversationId) {
    if (submissionFailure.value) return submissionFailure.value.message
  }
  return errorMessage(activeError.value)
})

async function initialize() {
  try { await store.initialize() } catch {}
}
async function createConversation() { try { await store.createConversation() } catch {} }
async function openConversation(conversationId) { try { if (conversationId !== store.activeConversationId) await store.openConversation(conversationId) } catch {} }
async function openFromDrawer(conversationId) { await openConversation(conversationId); drawerOpen.value = false }
async function renameConversation(conversationId, title) { try { await store.renameConversation(conversationId, title) } catch {} }
async function deleteConversation(conversationId) { try { await store.deleteConversation(conversationId) } catch {} }
async function sendPrompt(content, confirmStarted) {
  if (submitting.value || isGenerating.value) return
  const normalized = String(content || '').trim()
  if (!normalized) return

  submitting.value = true
  submissionFailure.value = null
  const pending = {
    content: normalized,
    confirmStarted: typeof confirmStarted === 'function' ? confirmStarted : pendingSubmission.value?.confirmStarted,
    conversationId: store.activeConversationId
  }
  pendingSubmission.value = pending

  try {
    let conversationId = store.activeConversationId
    if (conversationId == null) {
      const created = await store.createConversation(normalized.slice(0, 120))
      conversationId = created?.id
      if (conversationId == null) throw new Error('会话创建失败，请重试。')
      pending.conversationId = conversationId
    }

    const sending = store.sendMessage(conversationId, normalized)
    pending.confirmStarted?.()
    submitting.value = false
    await sending

    const streamError = store.errorByConversation[conversationId]
    if (streamError) {
      submissionFailure.value = { conversationId, message: errorMessage(streamError) }
      return
    }
    if (pendingSubmission.value === pending) pendingSubmission.value = null
  } catch (error) {
    submissionFailure.value = { conversationId: pending.conversationId, message: errorMessage(error) }
  } finally {
    submitting.value = false
  }
}
function retryPending() {
  if (!retryContent.value) return
  const confirmStarted = pendingSubmission.value?.confirmStarted
  void sendPrompt(retryContent.value, confirmStarted)
}
async function stopGeneration() { try { if (store.activeConversationId != null) await store.stopGeneration(store.activeConversationId) } catch {} }

function errorMessage(error) {
  if (!error) return ''
  return error?.message || String(error) || '发送失败，请重试。'
}

onMounted(initialize)
</script>

<style scoped>
.ai-workspace { display: flex; height: clamp(500px, 62vh, 680px); min-height: 0; overflow: hidden; flex-direction: column; border: 1px solid var(--ai-rule-strong); background: var(--surface-solid); box-shadow: var(--surface-shadow); }
.ai-workspace__header { display: flex; min-height: 54px; flex: 0 0 auto; align-items: center; justify-content: space-between; gap: 18px; padding: 9px 16px; border-bottom: 1px solid var(--ai-rule-strong); background: color-mix(in srgb, var(--brand-paper) 58%, var(--surface-solid)); }
.ai-workspace__title { display: flex; align-items: baseline; gap: 9px; white-space: nowrap; }
.ai-workspace__title span { color: var(--brand-vermilion); font: 11px var(--font-data); letter-spacing: .08em; }
.ai-workspace__title strong { color: var(--brand-ink); font: 700 16px var(--font-display); }
.ai-workspace__facts { display: flex; flex: 1; justify-content: flex-end; gap: 0; margin: 0; padding: 0; color: var(--el-text-color-secondary); font: 11px var(--font-data); list-style: none; }
.ai-workspace__facts li { padding: 0 10px; border-left: 1px solid var(--ai-rule-strong); }
.ai-workspace__facts li:first-child { border-left: 0; }
.ai-workspace__drawer-button { display: none; width: 58px; min-height: 30px; margin: 0; border-radius: var(--radius-xs); }
.ai-workspace__body { display: flex; min-height: 0; flex: 1; overflow: hidden; }
.ai-workspace__conversation { display: flex; min-width: 0; min-height: 0; flex: 1; overflow: hidden; flex-direction: column; }
.ai-workspace__state { display: grid; min-height: 0; flex: 1; align-content: center; gap: 16px; overflow: auto; padding: 24px; }
.ai-workspace__submission-error { display: flex; min-height: 42px; flex: 0 0 auto; align-items: center; justify-content: space-between; gap: 12px; padding: 6px 20px; border-top: 1px solid color-mix(in srgb, var(--el-color-danger) 32%, transparent); background: color-mix(in srgb, var(--el-color-danger) 6%, var(--surface-solid)); color: var(--el-color-danger); font-size: 12px; }
.ai-workspace__retry { width: 84px; min-height: 30px; margin: 0; }
.ai-workspace__drawer :deep(.el-drawer__body) { padding: 0; }
.ai-workspace__drawer .conversation-sidebar { width: 100%; min-width: 0; height: 100%; }
@media (max-width: 719px) { .ai-workspace { height: clamp(500px, 72vh, 640px); } .ai-workspace__header { gap: 10px; padding: 8px 12px; } .ai-workspace__facts { display: none; } .ai-workspace__drawer-button { display: inline-flex; } .ai-workspace__desktop-sidebar { display: none; } .ai-workspace__submission-error { padding-inline: 14px; } }
</style>
