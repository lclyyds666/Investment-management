<template>
  <section class="legal-page">
    <header class="legal-heading">
      <div><span>LEGAL CASES</span><h1>案件管理</h1></div>
      <div class="heading-actions">
        <el-button v-if="canExport" :icon="Download" :loading="exporting" @click="doExport">导出</el-button>
        <el-button v-if="canImport" :icon="Upload" @click="importDialog.open()">导入台账</el-button>
        <el-button v-if="canWrite" type="primary" :icon="Plus" @click="$router.push('/investment/legal-risk/cases/new')">新建草稿</el-button>
      </div>
    </header>

    <div class="filter-band">
      <el-input v-model="filters.keyword" clearable placeholder="案件编号 / 名称 / 法院案号" :prefix-icon="Search" @keyup.enter="search" />
      <el-select v-model="filters.stage" clearable placeholder="建档状态">
        <el-option label="草稿" value="draft" /><el-option label="正式案件" value="formal" />
      </el-select>
      <el-select v-model="filters.status" clearable placeholder="主状态">
        <el-option v-for="item in CASE_STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-input v-model="filters.court" clearable placeholder="受理法院" />
      <el-input v-if="canFilterOwnership" v-model="filters.company_name" clearable placeholder="所属公司" />
      <el-input v-if="canFilterOwnership" v-model="filters.organization_name" clearable placeholder="发起组织" />
      <el-button type="primary" :icon="Search" @click="search">查询</el-button>
      <el-button :icon="Refresh" @click="reset">重置</el-button>
    </div>

    <div class="table-shell" v-loading="loading">
      <el-table :data="page.items" stripe @row-dblclick="openDetail">
        <el-table-column label="案件编号" min-width="150">
          <template #default="{ row }"><span class="case-no">{{ row.case_no || '草稿未编号' }}</span></template>
        </el-table-column>
        <el-table-column prop="case_name" label="案件名称" min-width="220" show-overflow-tooltip />
        <el-table-column prop="company_name" label="所属公司" min-width="160" show-overflow-tooltip />
        <el-table-column prop="organization_name" label="发起组织" min-width="160" show-overflow-tooltip />
        <el-table-column prop="court" label="受理法院" min-width="160" show-overflow-tooltip />
        <el-table-column prop="court_case_no" label="法院案号" min-width="150" show-overflow-tooltip />
        <el-table-column label="主状态" width="110">
          <template #default="{ row }"><el-tag :type="row.stage === 'draft' ? 'info' : statusType(row.status)" effect="plain">{{ row.stage === 'draft' ? '草稿' : caseStatusLabel(row.status) }}</el-tag></template>
        </el-table-column>
        <el-table-column label="标的额（元）" width="150" align="right">
          <template #default="{ row }"><span class="amount">{{ money(row.subject_amount) }}</span></template>
        </el-table-column>
        <el-table-column label="更新时间" width="165">
          <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">查看</el-button>
            <el-button v-if="canWrite && !row.archived_at" link type="primary" @click="$router.push(`/investment/legal-risk/cases/${row.id}/edit`)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && !page.items.length" description="暂无符合条件的案件" />
      <el-pagination v-if="page.total" v-model:current-page="filters.page" v-model:page-size="filters.page_size" :total="page.total" layout="total, sizes, prev, pager, next" @change="load" />
    </div>
    <ImportDialog ref="importDialog" @imported="load" />
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { Download, Plus, Refresh, Search, Upload } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { exportCases, listCases } from '@/api/legalRisk'
import { usePortalStore } from '@/store/portal'
import { CASE_STATUS_OPTIONS, caseStatusLabel, cleanParams, money } from '@/constants/legalRisk'
import { LEGAL_CAPABILITIES, hasLegalCapability } from '@/utils/legalCapabilities'
import ImportDialog from './ImportDialog.vue'

const route = useRoute()
const router = useRouter()
const portalStore = usePortalStore()
const role = computed(() => portalStore.companyRole('investment'))
const hasCapability = (capability) => hasLegalCapability(role.value, capability, portalStore.isSuperuser, portalStore.assignments)
const canWrite = computed(() => hasCapability(LEGAL_CAPABILITIES.EDIT_CASE))
const canImport = computed(() => hasCapability(LEGAL_CAPABILITIES.IMPORT_EXPORT))
const canExport = computed(() => canImport.value || hasCapability(LEGAL_CAPABILITIES.EXPORT_MANAGEMENT))
const canFilterOwnership = computed(() => portalStore.isSuperuser || portalStore.assignments.some(
  (assignment) => assignment.organization_code === 'investment.legal_risk'
))
const loading = ref(false)
const exporting = ref(false)
const importDialog = ref()
const filters = reactive({
  keyword: '',
  stage: '',
  status: typeof route.query.status === 'string' ? route.query.status : '',
  court: '',
  company_name: '',
  organization_name: '',
  page: 1,
  page_size: 20
})
const page = reactive({ items: [], total: 0 })

const statusType = (status) => ({ review_filing: 'info', in_trial: 'warning', judged: 'primary', enforcement: 'warning', terminal: 'danger', closed: 'success' }[status] || 'info')
const formatTime = (value) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'
const openDetail = (row) => router.push(`/investment/legal-risk/cases/${row.id}`)

async function load() {
  loading.value = true
  try { Object.assign(page, await listCases(cleanParams(filters))) } finally { loading.value = false }
}
function search() { filters.page = 1; load() }
function reset() { Object.assign(filters, { keyword: '', stage: '', status: '', court: '', company_name: '', organization_name: '', page: 1, page_size: 20 }); load() }

async function doExport() {
  exporting.value = true
  try {
    const blob = await exportCases(cleanParams({ keyword: filters.keyword, status: filters.status, court: filters.court }))
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url; link.download = `法务案件-${new Date().toISOString().slice(0, 10)}.xlsx`; link.click()
    URL.revokeObjectURL(url)
  } finally { exporting.value = false }
}

watch(() => route.query.status, (status) => {
  filters.status = typeof status === 'string' ? status : ''
  filters.page = 1
  load()
})
onMounted(load)
</script>

<style scoped>
.legal-page { min-width: 0; }
.legal-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 18px; padding: 4px 0 16px 16px; border-bottom: 1px solid var(--el-border-color-lighter); border-left: 4px solid var(--brand-vermilion); }
.legal-heading span { color: var(--brand-vermilion); font-family: var(--font-data); font-size: 11px; letter-spacing: 0; }
.legal-heading h1 { margin: 4px 0 0; font-size: 25px; letter-spacing: 0; }
.heading-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.filter-band { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 14px; padding: 14px; border: 1px solid var(--el-border-color-lighter); background: var(--surface-solid); }
.table-shell { min-width: 0; padding: 14px; border: 1px solid var(--el-border-color-lighter); background: var(--surface-solid); overflow-x: auto; }
.case-no, .amount { font-family: var(--font-data); font-variant-numeric: tabular-nums; }
@media (max-width: 1100px) { .filter-band { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 680px) { .legal-heading { align-items: flex-start; flex-direction: column; } .heading-actions { justify-content: flex-start; } .filter-band { grid-template-columns: 1fr; } }
</style>
