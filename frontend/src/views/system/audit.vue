<template>
  <div class="audit-page">
    <section class="reassignment-audits" data-testid="reassignment-audits">
      <div class="reassignment-heading"><div><small>审批治理</small><h3>改派审计</h3></div><span>{{ reassignmentAudits.length }} 条记录</span></div>
      <el-alert v-if="reassignmentError" :title="reassignmentError" type="error" :closable="false" show-icon />
      <div v-if="reassignmentAudits.length" v-loading="reassignmentLoading" class="audit-track">
        <article v-for="entry in reassignmentAudits" :key="entry.id" class="reassignment-entry">
          <div class="audit-time">{{ fmtTime(entry.created_at) }}</div>
          <div class="audit-change"><strong>{{ entry.old_assignee_name || '原办理人' }} <b>→</b> {{ entry.new_assignee_name }}</strong><span>{{ entry.required_position_name || entry.required_position_code }}</span></div>
          <div class="audit-reason"><span>操作人 {{ entry.operator_name }}</span><p>{{ entry.reason }}</p></div>
        </article>
      </div>
      <el-empty v-else :image-size="42" description="暂无改派审计" />
      <div v-if="reassignmentTotal > reassignmentPageSize" class="pager">
        <el-pagination background layout="total, prev, pager, next" :total="reassignmentTotal" :current-page="reassignmentPage" :page-size="reassignmentPageSize" @current-change="onReassignmentPage" />
      </div>
    </section>
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
              <span v-if="isAuthorizationAudit(row)" class="who-position">{{ row.position_name || row.position_code || '岗位快照缺失' }}</span>
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
        <el-table-column label="目标" min-width="130" show-overflow-tooltip>
          <template #default="{ row }"><span v-if="isAuthorizationAudit(row)">{{ targetLabel(row) }}：{{ row.target_desc || '—' }}</span><span v-else>{{ row.target_desc }}</span></template>
        </el-table-column>
        <el-table-column label="授权变更" min-width="300">
          <template #default="{ row }">
            <div v-if="isAuthorizationAudit(row)" class="authorization-change" data-testid="authorization-audit-detail">
              <div>原因：{{ row.reason || '—' }}</div>
              <div class="change-tags"><span>变更前</span><el-tag v-for="item in snapshotTags(row, row.before_json, false)" :key="`before-${item}`" size="small" effect="plain">{{ item }}</el-tag><em v-if="!snapshotTags(row, row.before_json, false).length">无</em></div>
              <div class="change-tags"><span>变更后</span><el-tag v-for="item in snapshotTags(row, row.after_json, true)" :key="`after-${item}`" size="small" type="success" effect="plain">{{ item }}</el-tag><em v-if="!snapshotTags(row, row.after_json, true).length">{{ row.action === 'assignment_terminate' ? '已移除' : '无' }}</em></div>
            </div>
            <span v-else>—</span>
          </template>
        </el-table-column>
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
import { listReassignmentAudits } from '@/api/workflow'

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const meta = reactive({ actions: [], modules: [] })
const dateRange = ref([])
const reassignmentAudits = ref([])
const reassignmentTotal = ref(0)
const reassignmentPage = ref(1)
const reassignmentPageSize = 10
const reassignmentLoading = ref(false)
const reassignmentError = ref('')
const metaLoading = ref(false)
const metaError = ref('')

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
function isAuthorizationAudit(row) { return row?.module === 'organization_authorization' || ['assignment_replace', 'assignment_terminate', 'position_permissions_replace', 'position_update', 'organization_create', 'organization_update'].includes(row?.action) }
function targetLabel(row) { const target = String(row?.target_desc || ''); if (target.startsWith('user#')) return '目标用户'; if (target.startsWith('organization#')) return '目标组织'; if (target.startsWith('position#')) return '目标岗位'; return '目标对象' }
function snapshotTags(row, snapshot, isAfter) {
  if (!snapshot || (Array.isArray(snapshot) && !snapshot.length)) return []
  const items = Array.isArray(snapshot) ? snapshot : [snapshot]
  if (row.action.startsWith('assignment_')) return items.map(item => {
    const organization = item.organization_name || item.organization_code || item.organization?.name || item.organization?.code || ''
    const position = item.position_name || item.position_code || item.position?.name || item.position?.code || ''
    const term = item.valid_from ? `${item.valid_from}${item.valid_until ? ` 至 ${item.valid_until}` : ' 起'}` : ''
    const status = item.status ? ` / ${item.status}` : ''
    const governance = item.governance_scopes?.length ? ` / 治理 ${item.governance_scopes.map(scope => `${scope.scope_type}:${scope.scope_ref}`).join(',')}` : ''
    const external = item.external ? ` / 外聘 ${item.external.provider_name}${item.external.service_scopes?.length ? `(${item.external.service_scopes.join(',')})` : ''}` : ''
    return `${[organization, position].filter(Boolean).join(' / ')}${status}${term ? ` / ${term}` : ''}${governance}${external}`.trim()
  })
  if (row.action.startsWith('organization_')) return items.map(item => `组织：${item.code || '—'}${item.name ? ` / ${item.name}` : ''}${item.organization_type ? ` / ${item.organization_type}` : ''}${item.parent_code ? ` / 上级 ${item.parent_code}` : ''}${item.company_code ? ` / 公司 ${item.company_code}` : ''}${item.is_active === false ? ' / 停用' : ''}${Number.isInteger(item.sort_order) ? ` / 排序 ${item.sort_order}` : ''}`)
  if (['position_create', 'position_update'].includes(row.action)) return items.map(item => `岗位：${item.code || '—'}${item.name ? ` / ${item.name}` : ''}${item.category ? ` / ${item.category}` : ''}${item.is_active === false ? ' / 停用' : ' / 启用'}`)
  if (row.action === 'position_permissions_replace') return items.map(item => `权限：${item.permission_code || '—'}${item.data_scope ? ` / ${item.data_scope}` : ''}${item.scope_ref ? ` / ${item.scope_ref}` : ''}`)
  return isAfter ? ['已更新'] : ['原配置']
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

async function loadMeta() {
  metaLoading.value = true
  metaError.value = ''
  try {
    const result = await getAuditMeta()
    meta.actions = result.actions || []
    meta.modules = result.modules || []
  } catch {
    metaError.value = '筛选选项加载失败'
  } finally {
    metaLoading.value = false
  }
}

async function loadReassignmentAudits() {
  reassignmentLoading.value = true
  reassignmentError.value = ''
  try {
    const result = await listReassignmentAudits({ page: reassignmentPage.value, page_size: reassignmentPageSize })
    reassignmentAudits.value = result.items || []
    reassignmentTotal.value = result.total || 0
  } catch {
    reassignmentAudits.value = []
    reassignmentTotal.value = 0
    reassignmentError.value = '改派审计加载失败'
  } finally {
    reassignmentLoading.value = false
  }
}

async function onReassignmentPage(page) {
  reassignmentPage.value = page
  await loadReassignmentAudits()
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
  loadMeta()
  loadReassignmentAudits()
  load()
})

defineExpose({ meta, metaLoading, metaError, reassignmentAudits, reassignmentTotal, reassignmentLoading, reassignmentError, onReassignmentPage })
</script>

<style scoped lang="scss">
.audit-page { padding: 4px; }
.reassignment-audits { margin-bottom: 14px; padding: 16px; border: 1px solid var(--surface-border); border-top: 3px solid var(--brand-vermilion); background: var(--el-bg-color); }
.reassignment-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.reassignment-heading small { color: var(--brand-vermilion); font-weight: 700; }
.reassignment-heading h3 { margin: 3px 0 0; }
.reassignment-heading > span { color: var(--el-text-color-secondary); font-size: 12px; }
.audit-track { margin-top: 13px; border-left: 1px solid var(--el-border-color); }
.reassignment-entry { display: grid; grid-template-columns: 150px minmax(180px, .8fr) minmax(240px, 1.2fr); gap: 16px; position: relative; padding: 10px 12px 10px 18px; }
.reassignment-entry::before { content: ''; position: absolute; left: -5px; top: 15px; width: 8px; height: 8px; border: 1px solid var(--brand-vermilion); border-radius: 50%; background: var(--el-bg-color); }
.audit-time { color: var(--el-text-color-placeholder); font: 12px/1.5 'Consolas', monospace; }
.audit-change strong, .audit-change span, .audit-reason span { display: block; }
.audit-change strong { font-size: 13px; }
.audit-change strong b { margin: 0 7px; color: var(--brand-vermilion); }
.audit-change span, .audit-reason span { margin-top: 3px; color: var(--el-text-color-secondary); font-size: 12px; }
.audit-reason p { margin: 3px 0 0; font-size: 13px; }
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
.who-position { font-size: 12px; color: var(--brand-vermilion); }
.authorization-change { display: grid; gap: 5px; font-size: 12px; }
.change-tags { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; }
.change-tags > span { min-width: 42px; color: var(--el-text-color-secondary); }
.change-tags em { color: var(--el-text-color-placeholder); font-style: normal; }
.mono { font-family: 'Consolas', 'Monaco', monospace; font-size: 12px; }
.pager { margin-top: 12px; display: flex; justify-content: flex-end; }
@media (max-width: 760px) { .reassignment-entry { grid-template-columns: 1fr; gap: 5px; } }
</style>
