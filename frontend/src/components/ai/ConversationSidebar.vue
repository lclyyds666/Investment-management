<template>
  <aside class="conversation-sidebar" data-testid="conversation-sidebar" aria-label="会话索引">
    <header class="conversation-sidebar__header">
      <div><p>会话索引</p><span>{{ conversations.length }} 条记录</span></div>
      <el-button class="conversation-sidebar__new" type="primary" plain aria-label="新建会话" @click="$emit('create')">新建</el-button>
    </header>
    <nav class="conversation-sidebar__list" aria-label="历史会话">
      <div v-for="conversation in conversations" :key="conversation.id" class="conversation-sidebar__row" :class="{ 'is-active': conversation.id === activeId }">
        <input
          v-if="editingId === conversation.id"
          v-model="editingTitle"
          class="conversation-sidebar__rename"
          :aria-label="`重命名 ${conversation.title}`"
          @blur="completeRename(conversation)"
          @keydown.enter.prevent="completeRename(conversation)"
          @keydown.escape="cancelRename"
        >
        <button v-else class="conversation-sidebar__select" type="button" :aria-current="conversation.id === activeId ? 'page' : undefined" @click="$emit('select', conversation.id)">
          <span>{{ conversation.title || '未命名会话' }}</span>
          <small v-if="generating[conversation.id]">生成中</small>
        </button>
        <div class="conversation-sidebar__tools">
          <button type="button" :aria-label="`重命名 ${conversation.title}`" @click="beginRename(conversation)">改</button>
          <button type="button" :aria-label="`删除 ${conversation.title}`" @click="confirmDelete(conversation)">删</button>
        </div>
      </div>
      <p v-if="!conversations.length" class="conversation-sidebar__empty">新建会话后，将在这里保留记录。</p>
    </nav>
  </aside>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessageBox } from 'element-plus'

defineProps({
  conversations: { type: Array, default: () => [] },
  activeId: { type: [Number, String], default: null },
  generating: { type: Object, default: () => ({}) }
})
const emit = defineEmits(['create', 'select', 'rename', 'delete'])
const editingId = ref(null)
const editingTitle = ref('')

function beginRename(conversation) { editingId.value = conversation.id; editingTitle.value = conversation.title || '' }
function cancelRename() { editingId.value = null; editingTitle.value = '' }
function completeRename(conversation) {
  const title = editingTitle.value.trim()
  if (title && title !== conversation.title) emit('rename', conversation.id, title)
  cancelRename()
}
async function confirmDelete(conversation) {
  try {
    await ElMessageBox.confirm(`删除“${conversation.title || '未命名会话'}”后无法恢复。`, '删除会话', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
    emit('delete', conversation.id)
  } catch {}
}
</script>

<style scoped>
.conversation-sidebar { display: flex; width: var(--ai-sidebar-width); min-width: var(--ai-sidebar-width); flex-direction: column; border-right: 1px solid var(--ai-rule-strong); background: var(--surface-muted); }
.conversation-sidebar__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; padding: 16px; border-bottom: 1px solid var(--ai-rule); }
.conversation-sidebar__header p { margin: 0; color: var(--el-text-color-primary); font: 700 14px var(--font-display); }
.conversation-sidebar__header span { color: var(--el-text-color-secondary); font: 11px var(--font-data); }
.conversation-sidebar__new { width: 56px; min-height: 30px; margin: 0; border-radius: var(--radius-xs); }
.conversation-sidebar__list { flex: 1; overflow-y: auto; padding: 8px; }
.conversation-sidebar__row { display: flex; align-items: center; gap: 3px; border-bottom: 1px solid var(--ai-rule); }
.conversation-sidebar__row.is-active { background: color-mix(in srgb, var(--brand-lake) 9%, transparent); box-shadow: inset 2px 0 var(--brand-vermilion); }
.conversation-sidebar__select { flex: 1; min-width: 0; padding: 10px 6px 10px 8px; border: 0; background: transparent; color: var(--el-text-color-regular); cursor: pointer; font: 13px var(--font-body); text-align: left; }
.conversation-sidebar__select span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conversation-sidebar__select small { color: var(--brand-jade); font: 11px var(--font-data); }
.conversation-sidebar__tools { display: flex; opacity: .56; }
.conversation-sidebar__row:hover .conversation-sidebar__tools, .conversation-sidebar__row:focus-within .conversation-sidebar__tools { opacity: 1; }
.conversation-sidebar__tools button { width: 25px; height: 28px; padding: 0; border: 0; background: transparent; color: var(--el-text-color-secondary); cursor: pointer; font-size: 11px; }
.conversation-sidebar__tools button:hover { color: var(--brand-vermilion); }
.conversation-sidebar__rename { width: 100%; min-width: 0; margin: 6px 0 6px 5px; padding: 5px; border: 1px solid var(--brand-lake); border-radius: var(--radius-xs); background: var(--surface-solid); font: 13px var(--font-body); }
.conversation-sidebar__empty { margin: 20px 8px; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.65; }
</style>
