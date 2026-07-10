<template>
  <div class="channel" v-loading="loading">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>多渠道数据集成</span>
          <el-button :icon="Refresh" @click="load">刷新</el-button>
        </div>
      </template>

      <div class="grid">
        <el-card v-for="c in channels" :key="c.id" shadow="hover" class="ch-card">
          <div class="ch-top">
            <span class="ch-logo">{{ c.logo }}</span>
            <div class="ch-meta">
              <div class="ch-name">{{ c.name }}</div>
              <el-tag size="small" effect="plain">{{ c.category_label }}</el-tag>
            </div>
          </div>
          <div class="ch-desc">{{ c.description }}</div>

          <div class="ch-cred">
            <div class="cred-row">
              <span class="cred-label">账号</span>
              <span class="cred-val">{{ c.account }}</span>
              <el-button size="small" text :icon="CopyDocument" @click="copy(c.account)" />
            </div>
            <div class="cred-row">
              <span class="cred-label">密码</span>
              <span class="cred-val">{{ c.password }}</span>
              <el-button size="small" text :icon="CopyDocument" @click="copy(c.password)" />
            </div>
          </div>

          <div class="ch-actions">
            <el-button size="small" type="primary" :icon="Link" @click="openPlatform(c)">打开平台</el-button>
            <el-button size="small" :icon="Upload" @click="openData(c)">回传平台数据</el-button>
          </div>
        </el-card>
      </div>
    </el-card>

    <!-- 回传/导入数据抽屉 -->
    <el-drawer v-model="dataVisible" :title="`回传平台数据 - ${activeChannel?.name || ''}`" size="900px">
      <div class="data-toolbar">
        <el-upload action="#" :auto-upload="false" :show-file-list="false" accept=".csv,.txt" :on-change="onCsv">
          <el-button :icon="Upload">导入 CSV</el-button>
        </el-upload>
        <el-button :icon="MagicStick" @click="fillDemo">填充示例数据</el-button>
        <span class="flex-1"></span>
        <el-tag v-if="editable" type="success" effect="plain">可修改模式</el-tag>
        <el-button type="primary" :icon="Check" :disabled="!columns.length" :loading="saving" @click="save">
          保存数据
        </el-button>
      </div>

      <el-alert
        type="info" :closable="false" show-icon class="mb"
        title="导入外部平台导出的表格数据后，系统内表格切换为『可修改模式』，可直接编辑单元格并保存。"
      />

      <el-empty v-if="!columns.length" description="暂无数据，请导入 CSV 或填充示例数据" />
      <el-table v-else :data="rowObjs" border stripe size="small">
        <el-table-column v-for="(col, ci) in columns" :key="ci" :label="col" min-width="140">
          <template #default="{ row }">
            <el-input v-model="row.cells[ci]" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link :icon="Delete" @click="rows.splice($index, 1)" />
          </template>
        </el-table-column>
      </el-table>
      <div v-if="columns.length" class="add-row">
        <el-button size="small" :icon="Plus" @click="addRow">新增一行</el-button>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, CopyDocument, Link, Upload, Check, Delete, Plus, MagicStick } from '@element-plus/icons-vue'
import { listChannels, getChannelData, importChannelData } from '@/api/channel'

const loading = ref(false)
const channels = ref([])

async function load() {
  loading.value = true
  try { channels.value = await listChannels() } finally { loading.value = false }
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动复制：' + text)
  }
}
function openPlatform(c) {
  if (c.url) window.open(c.url, '_blank')
  else ElMessage.info('未配置平台地址')
}

/* 数据回传 */
const dataVisible = ref(false)
const activeChannel = ref(null)
const columns = ref([])
const rows = ref([]) // 每项 { cells: [...] }
const editable = ref(false)
const saving = ref(false)

const rowObjs = computed(() => rows.value)

async function openData(c) {
  activeChannel.value = c
  columns.value = []
  rows.value = []
  editable.value = false
  dataVisible.value = true
  const d = await getChannelData(c.id)
  columns.value = d.columns || []
  rows.value = (d.rows || []).map((r) => ({ cells: [...r] }))
  editable.value = columns.value.length > 0
}

function onCsv(file) {
  const reader = new FileReader()
  reader.onload = (e) => {
    parseCsv(String(e.target.result))
    ElMessage.success('已导入，进入可修改模式')
  }
  reader.readAsText(file.raw, 'utf-8')
}
function parseCsv(text) {
  const lines = text.split(/\r?\n/).filter((l) => l.trim())
  if (!lines.length) return
  columns.value = lines[0].split(',').map((s) => s.trim())
  rows.value = lines.slice(1).map((l) => ({ cells: l.split(',').map((s) => s.trim()) }))
  editable.value = true
}
function fillDemo() {
  columns.value = ['日期', '订单数', '核销数', '交易金额(元)']
  rows.value = [
    { cells: ['2026-06-01', '128', '120', '35600'] },
    { cells: ['2026-06-02', '96', '90', '28800'] },
    { cells: ['2026-06-03', '154', '150', '41200'] }
  ]
  editable.value = true
  ElMessage.success('已填充示例数据，进入可修改模式')
}
function addRow() {
  rows.value.push({ cells: columns.value.map(() => '') })
}
async function save() {
  saving.value = true
  try {
    const payloadRows = rows.value.map((r) => r.cells)
    await importChannelData(activeChannel.value.id, columns.value, payloadRows)
    ElMessage.success('数据已保存回传')
  } finally { saving.value = false }
}

onMounted(load)
</script>

<style scoped lang="scss">
.card-header { display: flex; justify-content: space-between; align-items: center; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.ch-card { :deep(.el-card__body) { padding: 16px; } }
.ch-top { display: flex; align-items: center; gap: 12px; }
.ch-logo { font-size: 34px; line-height: 1; }
.ch-name { font-size: 16px; font-weight: 700; color: #eafcff; margin-bottom: 4px; }
.ch-desc { margin: 12px 0; color: #909399; font-size: 13px; min-height: 20px; }
.ch-cred { background: rgba(28,155,230,0.08); border: 1px solid rgba(96,150,210,0.16); border-radius: 8px; padding: 8px 10px; margin-bottom: 12px; }
.cred-row { display: flex; align-items: center; gap: 8px; font-size: 13px; padding: 2px 0; }
.cred-label { color: #909399; width: 32px; flex: 0 0 auto; }
.cred-val { flex: 1; font-family: monospace; color: #7fd8ff; overflow: hidden; text-overflow: ellipsis; }
.ch-actions { display: flex; gap: 8px; }
.data-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.flex-1 { flex: 1; }
.mb { margin-bottom: 12px; }
.add-row { margin-top: 10px; }
</style>
