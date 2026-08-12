<template>
  <div ref="scroller" class="message-list" data-testid="message-list" aria-label="对话消息" tabindex="0" @scroll="savePosition">
    <div v-if="!messages.length" class="message-list__empty">
      <p>从权限内经营数据开始提问</p>
      <SuggestionList :suggestions="suggestions" @select="$emit('suggestion', $event)" />
    </div>
    <MessageBubble v-for="message in messages" :key="message.id" :message="message" />
    <el-alert v-if="error" class="message-list__error" type="error" :closable="false" :title="errorMessage" show-icon />
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import MessageBubble from './MessageBubble.vue'
import SuggestionList from './SuggestionList.vue'

const props = defineProps({
  conversationId: { type: [Number, String], default: null },
  messages: { type: Array, default: () => [] },
  suggestions: { type: Array, default: () => [] },
  error: { type: [Object, String], default: null },
  scrollPosition: { type: Number, default: 0 }
})
const emit = defineEmits(['save-scroll', 'suggestion'])
const scroller = ref(null)
const errorMessage = computed(() => props.error?.message || String(props.error || '请求失败，请稍后重试。'))

function savePosition() {
  if (props.conversationId != null) emit('save-scroll', props.conversationId, scroller.value?.scrollTop || 0)
}

watch(() => props.conversationId, async () => {
  await nextTick()
  if (scroller.value) scroller.value.scrollTop = props.scrollPosition
}, { immediate: true })

defineExpose({ scroller, savePosition })
</script>

<style scoped>
.message-list { display: flex; min-height: 0; flex: 1; flex-direction: column; gap: 14px; overflow-y: auto; padding: 18px 20px; background: color-mix(in srgb, var(--brand-paper) 38%, var(--surface-solid)); }
.message-list__empty { display: grid; min-height: 100%; place-content: center; gap: 12px; }
.message-list__empty > p { margin: 0; color: var(--el-text-color-secondary); font-size: 14px; text-align: center; }
.message-list__error { margin-top: auto; }
@media (max-width: 719px) { .message-list { padding: 14px; } }
</style>
