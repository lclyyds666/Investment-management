<template>
  <form class="composer" data-testid="message-composer" aria-label="发送问题" @submit.prevent="submit">
    <label class="composer__label" for="assistant-question">问题</label>
    <el-input
      id="assistant-question"
      v-model="draft"
      type="textarea"
      resize="none"
      :autosize="{ minRows: 2, maxRows: 4 }"
      :disabled="generating || submitting"
      placeholder="输入经营数据问题，按 Enter 发送"
      aria-label="输入问题"
      @compositionstart="composing = true"
      @compositionend="composing = false"
      @keydown="onKeydown"
    />
    <div class="composer__actions">
      <span class="composer__hint">Enter 发送 · Shift + Enter 换行</span>
      <el-button v-if="generating" class="composer__button" type="danger" plain native-type="button" aria-label="停止生成" @click="$emit('stop')">停止</el-button>
      <el-button v-else class="composer__button" type="primary" native-type="submit" :disabled="!normalizedDraft || submitting" aria-label="发送问题">
        {{ submitting ? '发送中' : '发送' }}
      </el-button>
    </div>
  </form>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({ generating: Boolean, submitting: Boolean })
const emit = defineEmits(['submit', 'stop'])
const draft = ref('')
const composing = ref(false)
const normalizedDraft = computed(() => draft.value.trim())

function submit() {
  if (!normalizedDraft.value || props.generating || props.submitting) return
  const content = normalizedDraft.value
  emit('submit', content, () => {
    if (draft.value.trim() === content) draft.value = ''
  })
}

function onKeydown(event) {
  if (event.key !== 'Enter' || event.shiftKey || event.isComposing || composing.value) return
  event.preventDefault()
  submit()
}
</script>

<style scoped>
.composer { display: grid; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--ai-rule-strong); background: var(--surface-solid); }
.composer__label { color: var(--el-text-color-secondary); font: 11px var(--font-data); letter-spacing: .04em; }
.composer :deep(.el-textarea__inner) { border-radius: var(--radius-xs); line-height: 1.55; }
.composer__actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.composer__hint { color: var(--el-text-color-secondary); font-size: 12px; }
.composer__button { width: 84px; min-height: 32px; margin: 0; }
@media (max-width: 719px) { .composer { padding: 12px 14px; } .composer__hint { font-size: 11px; } }
</style>
