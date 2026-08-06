<template>
  <article class="message" :class="`message--${message.role}`">
    <div class="message__identity" aria-hidden="true">
      <span>{{ message.role === 'user' ? '我' : 'AI' }}</span>
    </div>

    <div class="message__body">
      <div class="message__heading">
        <strong>{{ message.role === 'user' ? '我的问题' : '智能助手' }}</strong>
        <span v-if="statusLabel" class="message__status">{{ statusLabel }}</span>
      </div>

      <div v-if="message.role === 'assistant'" class="message__content markdown-body" v-html="safeContent" />
      <p v-else class="message__content message__content--plain">{{ message.content }}</p>

      <div v-if="toolStatuses.length" class="message__tools" aria-label="数据查询进度">
        <span v-for="item in toolStatuses" :key="`${item.tool}:${item.status}`">
          {{ toolLabel(item) }}
        </span>
      </div>

      <dl v-if="hasMetadata" class="message__metadata">
        <div v-if="requestedRange">
          <dt>查询范围</dt>
          <dd>{{ requestedRange }}</dd>
        </div>
        <div v-if="coveredRange">
          <dt>数据覆盖</dt>
          <dd>{{ coveredRange }}<span v-if="isPartialCoverage">（部分覆盖）</span></dd>
        </div>
        <div v-if="message.data_updated_at">
          <dt>更新时间</dt>
          <dd>{{ formatDateTime(message.data_updated_at) }}</dd>
        </div>
      </dl>

      <div v-if="validActions.length" class="message__actions" aria-label="可执行操作">
        <el-button
          v-for="action in validActions"
          :key="`${action.type}:${action.scenic_id}`"
          type="primary"
          plain
          :icon="Location"
          :aria-label="action.label"
          @click="navigate(action)"
        >
          {{ action.label }}
        </el-button>
      </div>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { Location } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { renderSafeMarkdown, validatedAction } from '@/utils/safeMarkdown'

const props = defineProps({
  message: {
    type: Object,
    required: true
  }
})

const router = useRouter()

const safeContent = computed(() => renderSafeMarkdown(props.message.content))
const validActions = computed(() => (
  (Array.isArray(props.message.actions_json) ? props.message.actions_json : [])
    .map(validatedAction)
    .filter(Boolean)
))
const toolStatuses = computed(() => (
  Array.isArray(props.message.tool_statuses) ? props.message.tool_statuses : []
))
const requestedRange = computed(() => formatRange(
  props.message.data_start_date,
  props.message.data_end_date
))
const coveredRange = computed(() => formatRange(
  props.message.data_covered_start,
  props.message.data_covered_end
))
const hasMetadata = computed(() => Boolean(
  requestedRange.value || coveredRange.value || props.message.data_updated_at
))
const isPartialCoverage = computed(() => Boolean(
  requestedRange.value
  && coveredRange.value
  && requestedRange.value !== coveredRange.value
))
const statusLabel = computed(() => ({
  generating: '生成中',
  stopped: '已停止',
  failed: '生成失败'
}[props.message.status] || ''))

function formatRange(start, end) {
  if (!start || !end) return ''
  return `${start} 至 ${end}`
}

function formatDateTime(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}

function toolLabel(item) {
  if (item.status === 'running') return '正在查询已授权数据'
  if (item.status === 'completed') return '数据查询完成'
  return '数据查询未完成'
}

function navigate(action) {
  router.push({
    name: 'CulturalTourismDetail',
    params: { scenicId: action.scenic_id }
  })
}
</script>

<style scoped>
.message {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.message__identity {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 1px solid var(--surface-border-strong);
  border-radius: var(--radius-xs);
  background: var(--surface-emphasis);
  color: var(--brand-lake);
  font-family: var(--font-data);
  font-size: 12px;
  font-weight: 750;
}

.message--user .message__identity {
  border-color: color-mix(in srgb, var(--brand-jade) 42%, transparent);
  background: color-mix(in srgb, var(--brand-jade) 10%, var(--surface-solid));
  color: var(--brand-jade);
}

.message__body {
  min-width: 0;
  padding: 13px 15px;
  border: 1px solid var(--surface-border);
  border-radius: var(--radius-sm);
  background: var(--surface-solid);
}

.message--user .message__body {
  background: var(--surface-muted);
}

.message__heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 7px;
  color: var(--el-text-color-primary);
  font-size: 13px;
}

.message__status {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: 500;
}

.message__content {
  margin: 0;
  color: var(--el-text-color-regular);
  font-size: 14px;
  line-height: 1.75;
}

.message__content--plain {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.markdown-body :deep(> :first-child) {
  margin-top: 0;
}

.markdown-body :deep(> :last-child) {
  margin-bottom: 0;
}

.markdown-body :deep(pre) {
  max-width: 100%;
  padding: 12px;
  overflow-x: auto;
  border-radius: var(--radius-xs);
  background: var(--el-fill-color-light);
}

.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  padding: 7px 9px;
  border: 1px solid var(--surface-border);
  text-align: left;
}

.message__tools,
.message__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 11px;
}

.message__tools span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.message__metadata {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 18px;
  margin: 12px 0 0;
  padding-top: 10px;
  border-top: 1px solid var(--surface-border);
}

.message__metadata div {
  display: flex;
  gap: 6px;
  min-width: 0;
  font-size: 12px;
}

.message__metadata dt {
  color: var(--el-text-color-secondary);
}

.message__metadata dd {
  margin: 0;
  color: var(--el-text-color-regular);
}

@media (max-width: 719px) {
  .message {
    grid-template-columns: 28px minmax(0, 1fr);
    gap: 8px;
  }

  .message__identity {
    width: 28px;
    height: 28px;
  }

  .message__body {
    padding: 11px 12px;
  }
}
</style>
