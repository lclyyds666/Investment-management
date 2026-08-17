<template>
  <section class="statistics-page">
    <header class="page-head">
      <div><span>CASE ANALYTICS</span><h1>案件统计</h1></div>
      <el-button :icon="Download" :loading="exporting" @click="doExport">导出当前口径</el-button>
    </header>

    <div class="filter-band">
      <el-input v-model="filters.keyword" clearable placeholder="案件编号 / 名称 / 法院案号" :prefix-icon="Search" @keyup.enter="load" />
      <el-input v-model="filters.court" clearable placeholder="受理法院" />
      <el-input-number v-model="filters.subject_amount_min" :min="0" :controls="false" placeholder="标的额下限" />
      <el-input-number v-model="filters.subject_amount_max" :min="0" :controls="false" placeholder="标的额上限" />
      <el-date-picker v-model="dateRange" type="daterange" value-format="YYYY-MM-DD" start-placeholder="建档起始" end-placeholder="建档截止" />
      <el-button type="primary" :icon="Search" @click="load">统计</el-button>
      <el-button :icon="Refresh" @click="reset">重置</el-button>
    </div>

    <div class="statistics-shell" v-loading="loading">
      <el-table :data="rows" stripe :row-class-name="({ row }) => row.status === 'total' ? 'total-row' : ''" @row-click="drill">
        <el-table-column prop="status_label" label="案件主状态" min-width="130" />
        <el-table-column prop="case_count" label="案件数" width="100" align="right" />
        <el-table-column label="占比" width="100" align="right"><template #default="{ row }">{{ percent(row.ratio) }}</template></el-table-column>
        <el-table-column label="标的额（元）" min-width="150" align="right"><template #default="{ row }"><span class="amount">{{ money(row.subject_amount) }}</span></template></el-table-column>
        <el-table-column label="累计回款（元）" min-width="150" align="right"><template #default="{ row }"><span class="amount">{{ money(row.recovered_amount) }}</span></template></el-table-column>
        <el-table-column label="待回款（元）" min-width="150" align="right"><template #default="{ row }"><span class="amount">{{ money(row.outstanding_amount) }}</span></template></el-table-column>
        <el-table-column prop="active_alert_count" label="活动预警" width="110" align="right" />
      </el-table>
      <p class="table-note">统计仅包含正式案件；固定展示六个主状态和合计。点击状态行可下钻案件明细。</p>
    </div>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Download, Refresh, Search } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { exportCases, getStatusStatistics } from '@/api/legalRisk'
import { cleanParams, money } from '@/constants/legalRisk'

const router = useRouter()
const loading = ref(false)
const exporting = ref(false)
const rows = ref([])
const dateRange = ref([])
const filters = reactive({ keyword: '', court: '', subject_amount_min: null, subject_amount_max: null })
const params = () => cleanParams({ ...filters, activated_from: dateRange.value?.[0], activated_to: dateRange.value?.[1] })
const percent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`

async function load() { loading.value = true; try { rows.value = await getStatusStatistics(params()) } finally { loading.value = false } }
function reset() { Object.assign(filters, { keyword: '', court: '', subject_amount_min: null, subject_amount_max: null }); dateRange.value = []; load() }
function drill(row) { if (row.status !== 'total') router.push({ path: '/investment/legal-risk/cases', query: { status: row.status } }) }
async function doExport() {
  exporting.value = true
  try {
    const blob = await exportCases(params())
    const url = URL.createObjectURL(blob); const link = document.createElement('a')
    link.href = url; link.download = `法务案件统计-${new Date().toISOString().slice(0, 10)}.xlsx`; link.click(); URL.revokeObjectURL(url)
  } finally { exporting.value = false }
}
onMounted(load)
</script>

<style scoped>
.page-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; margin-bottom: 16px; padding: 4px 0 16px 16px; border-bottom: 1px solid var(--el-border-color-lighter); border-left: 4px solid var(--brand-vermilion); }
.page-head span { color: var(--brand-vermilion); font-family: var(--font-data); font-size: 11px; letter-spacing: 0; }
.page-head h1 { margin: 4px 0 0; font-size: 25px; letter-spacing: 0; }
.filter-band { display: grid; grid-template-columns: 1.5fr 1fr 1fr 1fr minmax(260px, 1.3fr) auto auto; gap: 10px; margin-bottom: 14px; padding: 14px; border: 1px solid var(--el-border-color-lighter); background: var(--surface-solid); }
.filter-band :deep(.el-input-number), .filter-band :deep(.el-date-editor) { width: 100%; }
.statistics-shell { min-width: 0; padding: 14px; border: 1px solid var(--el-border-color-lighter); background: var(--surface-solid); overflow-x: auto; }
.amount { font-family: var(--font-data); font-variant-numeric: tabular-nums; }
:deep(.total-row td) { font-weight: 750; background: var(--surface-emphasis) !important; }
.table-note { margin: 12px 0 0; color: var(--el-text-color-secondary); font-size: 12px; }
@media (max-width: 1180px) { .filter-band { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 700px) { .filter-band { grid-template-columns: 1fr; } }
</style>
