<template>
  <div class="detail-files" v-loading="loading">
    <div class="df-head">
      <span class="df-tip">仅保存对账明细源文件，不解析明细内容；点击文件名可查看或下载。</span>
      <el-button size="small" :icon="Refresh" @click="load">刷新</el-button>
    </div>

    <div v-if="files.length" class="df-list">
      <div v-for="f in files" :key="f.key" class="df-item">
        <el-icon class="df-icon"><Document /></el-icon>
        <!-- 文件名：点击即在线查看 -->
        <a class="df-name" :title="f.name" @click="onView(f)">{{ f.name }}</a>
        <span class="df-period">{{ f.period }}</span>
        <el-button size="small" text type="primary" :icon="View" @click="onView(f)">查看</el-button>
        <el-button size="small" text type="success" :icon="Download" @click="onDownload(f)">下载</el-button>
      </div>
    </div>
    <el-empty v-else description="暂无对账明细源文件（上传对账明细并保存台账后在此展示）" :image-size="70" />
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Document, View, Download } from '@element-plus/icons-vue'
import { getTicketLedger, fetchTicketDetailBlob } from '@/api/ticketLedger'
import { downloadBlob, previewBlob } from '@/utils/file'

const props = defineProps({
  scenicId: { type: String, required: true }
})

const loading = ref(false)
const files = ref([])

async function load() {
  if (!props.scenicId) return
  loading.value = true
  try {
    const res = await getTicketLedger(props.scenicId)
    // 仅取已落盘的明细源文件；按核对日期(台账已排序)展示，去重同一文件
    const seen = new Set()
    files.value = (res.rows || [])
      .filter((r) => r.detail_stored)
      .map((r) => ({
        key: r.detail_stored,
        stored: r.detail_stored,
        name: r.detail_name || r.source_file || '对账明细.xlsx',
        period: r.check_date_text || ''
      }))
      .filter((f) => (seen.has(f.key) ? false : seen.add(f.key)))
  } catch {
    files.value = []
  } finally {
    loading.value = false
  }
}

async function onView(f) {
  try {
    const blob = await fetchTicketDetailBlob(props.scenicId, f.stored, f.name)
    previewBlob(blob, f.name)
  } catch {
    ElMessage.error('查看失败')
  }
}
async function onDownload(f) {
  try {
    const blob = await fetchTicketDetailBlob(props.scenicId, f.stored, f.name)
    downloadBlob(blob, f.name)
  } catch {
    ElMessage.error('下载失败')
  }
}

// 暴露给父组件：保存新台账后可主动刷新
defineExpose({ load })

watch(() => props.scenicId, load, { immediate: true })
</script>

<style scoped lang="scss">
.detail-files { margin-top: 4px; }
.df-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.df-tip { font-size: 12px; color: var(--el-text-color-secondary); }
.df-list { display: flex; flex-direction: column; gap: 6px; }
.df-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
  transition: border-color 0.2s, background 0.2s;
  &:hover { border-color: var(--el-color-primary); background: var(--el-fill-color-light); }
}
.df-icon { color: var(--el-color-success); font-size: 18px; flex-shrink: 0; }
.df-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
  cursor: pointer;
  text-decoration: none;
  &:hover { text-decoration: underline; }
}
.df-period { font-size: 12px; color: var(--el-text-color-secondary); flex-shrink: 0; }
</style>
