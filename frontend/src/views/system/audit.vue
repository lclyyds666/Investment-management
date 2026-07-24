<template>
  <div class="audit-page">
    <el-card shadow="never">
      <template #header>
        <div class="hdr">
          <span><el-icon><Document /></el-icon> 操作日志</span>
          <span class="hdr-sub">登录日志 + 系统写操作留痕（仅超级管理员可见）</span>
        </div>
      </template>

      <!-- 筛选栏 -->
      <el-form :inline="true" class="filters" @submit.prevent>
        <el-form-item label="关键词">
          <el-input v-model="filters.keyword" placeholder="用户/路径/目标/IP" clearable style="width: 200px" @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item label="模块">
          <el-select v-model="filters.module" placeholder="全部" clearable style="width: 130px">
            <el-option v-for="m in meta.modules" :key="m.value" :label="m.label" :value="m.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="动作">
          <el-select v-model="filters.action" placeholder="全部" clearable style="width: 130px">
            <el-option v-for="a in meta.actions" :key="a.value" :label="a.label" :value="a.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="结果">
          <el-select v-model="filters.status" placeholder="全部" clearable style="width: 110px">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="fail" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间">
          <el-date-picker
            v-model="dateRange" type="daterange" value-format="YYYY-MM-DD"
            range-separator="至" start-placeholder="开始" end-placeholder="结束" style="width: 240px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
          <el-button :icon="Refresh" @click="onReset">重置</el-button>
          <el-button type="success" plain :icon="Download" :disabled="!total" @click="onExport">导出CSV</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="rows" border stripe size="small" v-loading="loading" max-height="62vh">
        <el-table-column label="时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作者" width="170">
          <template #default="{ row }">
            <div class="who">
              <span class="who-name">{{ row.full_name || '—' }}</span>
              <span class="who-acct">{{ row.username }}<span v-if="row.role"> · {{ roleLabel(row.role) }}</span></span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="模块" width="100">
          <template #default="{ row }">{{ moduleLabel(row.module) }}</template>
        </el-table-column>
        <el-table-column label="动作" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="actionType(row.action)" effect="plain">{{ actionLabel(row.action) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="目标" min-width="130" prop="target_desc" show-overflow-tooltip />
        <el-table-column label="方法+路径" min-width="240" show-overflow-tooltip>
          <template #default="{ row }"><span class="mono">{{ row.method }} {{ row.path }}</span></template>
        </el-table-column>
        <el-table-column label="IP" width="130" prop="ip" show-overflow-tooltip />
        <el-table-column label="结果" width="90" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'success' ? 'success' : 'danger'">
              {{ row.status === 'success' ? '成功' : '失败' }}<span v-if="row.http_status"> {{ row.http_status }}</span>
            </el-tag>
          </template>
        </el-table-column>
        <template #empty>暂无审计记录</template>
      </el-table>

      <div class="pager">
        <el-pagination
          background layout="total, sizes, prev, pager, next, jumper"
          :total="total" :current-page="filters.page" :page-size="filters.size"
          :page-sizes="[20, 50, 100, 200]"
          @current-change="onPage" @size-change="onSize"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, Search, Refresh, Download } from '@element-plus/icons-vue'
import { listAuditLogs, getAuditMeta, fetchAuditExportBlob } from '@/api/audit'
import { roleLabel } from '@/constants/business'
import { downloadBlob } from '@/utils/file'

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const meta = reactive({ actions: [], modules: [] })
const dateRange = ref([])

const filters = reactive({
  keyword: '', module: '', action: '', status: '', method: '',
  start: '', end: '', page: 1, size: 20
})

const actionMap = computed(() => Object.fromEntries(meta.actions.map((a) => [a.value, a.label])))
const moduleMap = computed(() => Object.fromEntries(meta.modules.map((m) => [m.value, m.label])))
function actionLabel(v) { return actionMap.value[v] || v || '—' }
function moduleLabel(v) { return moduleMap.value[v] || v || '—' }
function fmtTime(t) { return t ? String(t).replace('T', ' ').slice(0, 19) : '—' }
function actionType(a) {
  if (['delete', 'reject', 'login_failed'].includes(a)) return 'danger'
  if (['create', 'approve', 'login'].includes(a)) return 'success'
  if (['update', 'submit', 'reset_password', 'toggle_active'].includes(a)) return 'warning'
  return 'info'
}

function buildParams() {
  return {
    keyword: filters.keyword || undefined,
    module: filters.module || undefined,
    action: filters.action || undefined,
    status: filters.status || undefined,
    start: dateRange.value?.[0] || undefined,
    end: dateRange.value?.[1] || undefined,
    page: filters.page, size: filters.size
  }
}

async function load() {
  loading.value = true
  try {
    const res = await listAuditLogs(buildParams())
    rows.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

function onSearch() { filters.page = 1; load() }
function onReset() {
  filters.keyword = filters.module = filters.action = filters.status = ''
  dateRange.value = []
  filters.page = 1
  load()
}
function onPage(p) { filters.page = p; load() }
function onSize(s) { filters.size = s; filters.page = 1; load() }

async function onExport() {
  try {
    const p = buildParams(); delete p.page; delete p.size
    const blob = await fetchAuditExportBlob(p)
    downloadBlob(blob, `操作日志_${new Date().toISOString().slice(0, 10)}.csv`)
  } catch {
    ElMessage.error('导出失败')
  }
}

onMounted(async () => {
  try { const m = await getAuditMeta(); meta.actions = m.actions || []; meta.modules = m.modules || [] } catch { /* 忽略 */ }
  load()
})
</script>

<style scoped lang="scss">
.audit-page { padding: 4px; }
.hdr {
  display: flex;
  align-items: baseline;
  gap: 12px;
  .el-icon { color: var(--el-color-primary); vertical-align: -2px; margin-right: 4px; }
}
.hdr-sub { font-size: 12px; color: var(--el-text-color-secondary); font-weight: 400; }
.filters { margin-bottom: 6px; }
.who { display: flex; flex-direction: column; line-height: 1.3; }
.who-name { font-weight: 600; }
.who-acct { font-size: 12px; color: var(--el-text-color-secondary); }
.mono { font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; }
.pager { margin-top: 12px; display: flex; justify-content: flex-end; }
</style>
