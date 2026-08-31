<template>
  <section class="fund-page">
    <header class="page-heading">
      <div>
        <span>FUND LEDGER</span>
        <h1>资金管理</h1>
        <p>资金增减、占用与到期风险统一登记</p>
      </div>
      <el-button v-if="canWrite" type="primary" :icon="Plus" @click="openCreate">新增流水</el-button>
    </header>

    <div class="summary-grid" v-loading="summaryLoading">
      <el-card shadow="never" class="summary-card balance" :class="{ risk: Number(summary.available_funds) < 0 }">
        <div class="summary-index">01</div>
        <div class="summary-label">可使用资金</div>
        <div class="summary-value">{{ formatAmount(summary.available_funds) }}</div>
        <div class="summary-note">累计增加减去已使用资金</div>
      </el-card>
      <el-card shadow="never" class="summary-card increase">
        <div class="summary-index">02</div>
        <div class="summary-label">累计增加</div>
        <div class="summary-value">{{ formatAmount(summary.total_increase) }}</div>
        <div class="summary-note">授信、借款、回款及自有资金</div>
      </el-card>
      <el-card shadow="never" class="summary-card usage">
        <div class="summary-index">03</div>
        <div class="summary-label">已使用资金</div>
        <div class="summary-value">{{ formatAmount(summary.total_usage) }}</div>
        <div class="summary-note">业务付款、费用及还本付息</div>
      </el-card>
      <el-card shadow="never" class="summary-card due" :class="{ warning: Number(summary.due_within_30_amount) > 0 }">
        <div class="summary-index">04</div>
        <div class="summary-label">30 天内到期</div>
        <div class="summary-value">{{ formatAmount(summary.due_within_30_amount) }}</div>
        <div class="summary-note">
          {{ summary.due_within_30_count || 0 }} 笔即将到期
          <span v-if="summary.overdue_count" class="overdue-note">· {{ summary.overdue_count }} 笔已逾期</span>
        </div>
      </el-card>
    </div>

    <div class="filter-band">
      <el-select v-model="filters.direction" clearable placeholder="资金方向" @change="onFilterDirectionChange">
        <el-option label="资金增加" value="increase" />
        <el-option label="资金使用" value="usage" />
      </el-select>
      <el-select v-model="filters.category" clearable placeholder="资金类型">
        <el-option v-for="item in filterCategoryOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.settlement_status" clearable placeholder="结清状态">
        <el-option label="未结清" value="open" />
        <el-option label="已结清" value="settled" />
      </el-select>
      <el-select v-model="filters.maturity_status" clearable placeholder="到期状态">
        <el-option label="正常" value="normal" />
        <el-option label="30 天内到期" value="due_soon" />
        <el-option label="已逾期" value="overdue" />
        <el-option label="已结清" value="settled" />
      </el-select>
      <el-date-picker
        v-model="filters.dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="至"
        start-placeholder="发生日期起"
        end-placeholder="发生日期止"
      />
      <el-input v-model="filters.keyword" clearable placeholder="对方单位 / 用途 / 备注" :prefix-icon="Search" @keyup.enter="search" />
      <div class="filter-actions">
        <el-button type="primary" :icon="Search" @click="search">查询</el-button>
        <el-button :icon="Refresh" @click="resetFilters">重置</el-button>
      </div>
    </div>

    <el-card shadow="never" class="ledger-card">
      <template #header>
        <div class="ledger-header">
          <div>
            <strong>资金流水台账</strong>
            <span>共 {{ page.total }} 条</span>
          </div>
          <el-button :icon="Refresh" :loading="loading" @click="loadLedger">刷新</el-button>
        </div>
      </template>

      <el-table v-loading="loading" :data="page.items" stripe empty-text="暂无资金流水">
        <el-table-column prop="occurred_on" label="发生日期" width="115" />
        <el-table-column label="方向" width="100">
          <template #default="{ row }">
            <el-tag :type="row.direction === 'increase' ? 'success' : 'warning'" effect="plain">
              {{ directionLabel(row.direction) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="120">
          <template #default="{ row }">{{ categoryLabel(row.category) }}</template>
        </el-table-column>
        <el-table-column label="金额（万元）" width="150" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ formatAmount(row.amount) }}</span></template>
        </el-table-column>
        <el-table-column prop="counterparty" label="对方单位" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.counterparty || '—' }}</template>
        </el-table-column>
        <el-table-column prop="summary" label="用途 / 摘要" min-width="190" show-overflow-tooltip>
          <template #default="{ row }">{{ row.summary || '—' }}</template>
        </el-table-column>
        <el-table-column label="到期日" width="115">
          <template #default="{ row }">{{ row.maturity_date || '—' }}</template>
        </el-table-column>
        <el-table-column label="到期状态" width="115">
          <template #default="{ row }">
            <el-tag :type="maturityType(row.maturity_status)" effect="plain">
              {{ maturityLabel(row.maturity_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结清状态" width="105">
          <template #default="{ row }">
            <el-tag :type="row.settlement_status === 'settled' ? 'success' : 'info'" effect="plain">
              {{ row.settlement_status === 'settled' ? '已结清' : '未结清' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="canWrite" label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canSettle(row)" link type="success" :icon="CircleCheck" @click="onSettle(row)">结清</el-button>
            <el-button link type="danger" :icon="Delete" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-if="page.total"
        v-model:current-page="filters.page"
        v-model:page-size="filters.page_size"
        :page-sizes="[10, 20, 50, 100]"
        :total="page.total"
        layout="total, sizes, prev, pager, next"
        @current-change="loadLedger"
        @size-change="onPageSizeChange"
      />
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑资金流水' : '新增资金流水'" width="680px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="104px">
        <div class="form-grid">
          <el-form-item label="资金方向" prop="direction">
            <el-radio-group v-model="form.direction" :disabled="editingSettled" @change="onFormDirectionChange">
              <el-radio-button value="increase">资金增加</el-radio-button>
              <el-radio-button value="usage">资金使用</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="资金类型" prop="category">
            <el-select v-model="form.category" :disabled="editingSettled" placeholder="请选择类型" style="width: 100%">
              <el-option v-for="item in formCategoryOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="金额（万元）" prop="amountWan">
            <el-input-number v-model="form.amountWan" :min="0.000001" :precision="6" :step="1" controls-position="right" style="width: 100%" />
          </el-form-item>
          <el-form-item label="发生日期" prop="occurred_on">
            <el-date-picker v-model="form.occurred_on" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
          <el-form-item label="到期日期" :required="requiresMaturity">
            <el-date-picker v-model="form.maturity_date" type="date" value-format="YYYY-MM-DD" clearable style="width: 100%" />
          </el-form-item>
          <el-form-item label="对方单位" prop="counterparty">
            <el-input v-model="form.counterparty" maxlength="200" placeholder="银行、公司或客户名称" />
          </el-form-item>
        </div>
        <el-form-item label="用途 / 摘要" prop="summary">
          <el-input v-model="form.summary" maxlength="300" placeholder="说明资金来源或具体用途" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="3" placeholder="可补充合同、批次等追溯信息" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitForm">保存流水</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { CircleCheck, Delete, Edit, Plus, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createFund,
  deleteFund,
  getFundSummary,
  listFunds,
  settleFund,
  updateFund
} from '@/api/fund'
import { usePortalStore } from '@/store/portal'
import { canUsePermission } from '@/utils/businessAuthorization'
import { formatWanFromYuan, wanToYuan, yuanToWan } from '@/utils/money'

const CATEGORY_OPTIONS = Object.freeze({
  increase: [
    { label: '银行授信', value: 'bank_credit' },
    { label: '公司借款', value: 'company_loan' },
    { label: '客户回款', value: 'customer_payment' },
    { label: '自有资金', value: 'own_funds' },
    { label: '其他', value: 'other' }
  ],
  usage: [
    { label: '业务付款', value: 'business_payment' },
    { label: '费用支出', value: 'expense' },
    { label: '还本付息', value: 'principal_interest_payment' },
    { label: '其他', value: 'other' }
  ]
})
const DUE_CATEGORIES = new Set(['bank_credit', 'company_loan'])

const portalStore = usePortalStore()
const canWrite = computed(() => canUsePermission(portalStore, 'supply.finance.update'))
const loading = ref(false)
const summaryLoading = ref(false)
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const editingSettled = ref(false)
const formRef = ref()
const lockedClassification = reactive({ direction: '', category: '' })
const summary = reactive({
  available_funds: 0,
  total_increase: 0,
  total_usage: 0,
  due_within_30_amount: 0,
  due_within_30_count: 0,
  overdue_count: 0
})
const page = reactive({ items: [], total: 0, page: 1, page_size: 20 })
const filters = reactive({
  direction: '',
  category: '',
  settlement_status: '',
  maturity_status: '',
  dateRange: [],
  keyword: '',
  page: 1,
  page_size: 20
})

function todayString() {
  const today = new Date()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  return `${today.getFullYear()}-${month}-${day}`
}

function emptyForm() {
  return {
    direction: 'increase',
    category: 'customer_payment',
    amountWan: null,
    occurred_on: todayString(),
    counterparty: '',
    summary: '',
    maturity_date: null,
    remark: ''
  }
}

const form = reactive(emptyForm())
const formCategoryOptions = computed(() => CATEGORY_OPTIONS[form.direction] || [])
const filterCategoryOptions = computed(() => {
  if (filters.direction) return CATEGORY_OPTIONS[filters.direction] || []
  const options = [...CATEGORY_OPTIONS.increase, ...CATEGORY_OPTIONS.usage]
  return options.filter((item, index) => options.findIndex((candidate) => candidate.value === item.value) === index)
})
const effectiveCategory = computed(() => editingSettled.value ? lockedClassification.category : form.category)
const requiresMaturity = computed(() => DUE_CATEGORIES.has(effectiveCategory.value))
const rules = {
  direction: [{ required: true, message: '请选择资金方向', trigger: 'change' }],
  category: [{ required: true, message: '请选择资金类型', trigger: 'change' }],
  amountWan: [
    { required: true, message: '请输入金额', trigger: 'blur' },
    { type: 'number', min: 0.000001, message: '金额必须大于 0', trigger: 'blur' }
  ],
  occurred_on: [{ required: true, message: '请选择发生日期', trigger: 'change' }]
}

function formatAmount(value) {
  return formatWanFromYuan(value)
}

function directionLabel(direction) {
  return direction === 'increase' ? '资金增加' : '资金使用'
}

function categoryLabel(category) {
  const option = [...CATEGORY_OPTIONS.increase, ...CATEGORY_OPTIONS.usage].find((item) => item.value === category)
  return option?.label || category || '—'
}

function maturityLabel(status) {
  return ({ normal: '正常', due_soon: '即将到期', overdue: '已逾期', settled: '已结清' })[status] || '正常'
}

function maturityType(status) {
  return ({ due_soon: 'warning', overdue: 'danger', settled: 'success', normal: 'info' })[status] || 'info'
}

function cleanFilterParams() {
  const params = {
    direction: filters.direction,
    category: filters.category,
    settlement_status: filters.settlement_status,
    maturity_status: filters.maturity_status,
    start_date: filters.dateRange?.[0],
    end_date: filters.dateRange?.[1],
    keyword: filters.keyword?.trim(),
    page: filters.page,
    page_size: filters.page_size
  }
  return Object.fromEntries(Object.entries(params).filter(([, value]) => value !== '' && value != null))
}

async function loadLedger() {
  loading.value = true
  try {
    const result = await listFunds(cleanFilterParams())
    Object.assign(page, result || { items: [], total: 0, page: filters.page, page_size: filters.page_size })
    filters.page = page.page || filters.page
  } finally {
    loading.value = false
  }
}

async function loadSummary() {
  summaryLoading.value = true
  try {
    Object.assign(summary, await getFundSummary())
  } finally {
    summaryLoading.value = false
  }
}

async function search() {
  filters.page = 1
  await loadLedger()
}

async function resetFilters() {
  Object.assign(filters, {
    direction: '',
    category: '',
    settlement_status: '',
    maturity_status: '',
    dateRange: [],
    keyword: '',
    page: 1,
    page_size: 20
  })
  await loadLedger()
}

function onFilterDirectionChange() {
  const allowed = CATEGORY_OPTIONS[filters.direction]
  if (allowed && !allowed.some((item) => item.value === filters.category)) filters.category = ''
}

function onFormDirectionChange() {
  if (editingSettled.value) {
    form.direction = lockedClassification.direction
    form.category = lockedClassification.category
    return
  }
  const allowed = CATEGORY_OPTIONS[form.direction] || []
  if (!allowed.some((item) => item.value === form.category)) form.category = allowed[0]?.value || ''
  if (!DUE_CATEGORIES.has(form.category)) form.maturity_date = null
}

async function onPageSizeChange() {
  filters.page = 1
  await loadLedger()
}

function openCreate() {
  if (!canWrite.value) return
  editingId.value = null
  editingSettled.value = false
  Object.assign(lockedClassification, { direction: '', category: '' })
  Object.assign(form, emptyForm())
  formRef.value?.clearValidate?.()
  dialogVisible.value = true
}

function openEdit(row) {
  if (!canWrite.value) return
  editingId.value = row.id
  editingSettled.value = row.settlement_status === 'settled'
  Object.assign(lockedClassification, { direction: row.direction, category: row.category })
  Object.assign(form, {
    direction: row.direction,
    category: row.category,
    amountWan: yuanToWan(row.amount),
    occurred_on: row.occurred_on,
    counterparty: row.counterparty || '',
    summary: row.summary || '',
    maturity_date: row.maturity_date || null,
    remark: row.remark || ''
  })
  formRef.value?.clearValidate?.()
  dialogVisible.value = true
}

function transactionPayload() {
  return {
    direction: editingSettled.value ? lockedClassification.direction : form.direction,
    category: editingSettled.value ? lockedClassification.category : form.category,
    amount: wanToYuan(form.amountWan),
    occurred_on: form.occurred_on,
    counterparty: form.counterparty?.trim() || '',
    summary: form.summary?.trim() || '',
    maturity_date: form.maturity_date || null,
    remark: form.remark?.trim() || ''
  }
}

async function submitForm() {
  if (saving.value || !canWrite.value) return
  if (requiresMaturity.value && !form.maturity_date) {
    ElMessage.error('银行授信和公司借款必须填写到期日')
    return
  }
  if (form.maturity_date && form.occurred_on && form.maturity_date < form.occurred_on) {
    ElMessage.error('到期日期不能早于发生日期')
    return
  }
  const valid = await formRef.value?.validate?.().catch(() => false)
  if (valid === false) return

  saving.value = true
  try {
    const payload = transactionPayload()
    if (editingId.value) {
      await updateFund(editingId.value, payload)
      ElMessage.success('资金流水已更新')
    } else {
      await createFund(payload)
      ElMessage.success('资金流水已新增')
    }
    dialogVisible.value = false
    await Promise.all([loadLedger(), loadSummary()])
  } finally {
    saving.value = false
  }
}

function canSettle(row) {
  return canWrite.value && DUE_CATEGORIES.has(row.category) && row.settlement_status === 'open'
}

async function onSettle(row) {
  if (!canSettle(row)) return
  try {
    await ElMessageBox.confirm(
      `确认将“${categoryLabel(row.category)}”记录标记为已结清？结清不会自动冲减资金余额。`,
      '结清确认',
      { type: 'warning', confirmButtonText: '确认结清', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await settleFund(row.id, todayString())
  ElMessage.success('资金已结清')
  await Promise.all([loadLedger(), loadSummary()])
}

async function onDelete(row) {
  if (!canWrite.value) return
  try {
    await ElMessageBox.confirm(
      `确定删除 ${row.occurred_on} 的“${categoryLabel(row.category)}”资金流水吗？删除后无法恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await deleteFund(row.id)
  ElMessage.success('资金流水已删除')
  await Promise.all([loadLedger(), loadSummary()])
}

onMounted(() => Promise.all([loadLedger(), loadSummary()]))
</script>

<style scoped lang="scss">
.fund-page { min-width: 0; }
.page-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
  padding: 4px 0 16px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  border-left: 4px solid var(--brand-vermilion);
}
.page-heading span { color: var(--brand-vermilion); font-family: var(--font-data); font-size: 11px; }
.page-heading h1 { margin: 4px 0 0; font-size: 25px; }
.page-heading p { margin: 6px 0 0; color: var(--el-text-color-secondary); font-size: 13px; }
.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 16px; }
.summary-card { position: relative; overflow: hidden; border-top: 3px solid var(--el-color-primary); }
.summary-card.increase { border-top-color: var(--el-color-success); }
.summary-card.usage { border-top-color: var(--el-color-info); }
.summary-card.due { border-top-color: var(--el-border-color); }
.summary-card.risk { border-top-color: var(--el-color-danger); background: var(--el-color-danger-light-9); }
.summary-card.warning { border-top-color: var(--el-color-warning); background: var(--el-color-warning-light-9); }
.summary-index { position: absolute; top: 13px; right: 15px; color: var(--el-border-color); font: 700 12px/1 var(--font-data); }
.summary-label { color: var(--el-text-color-secondary); font-size: 13px; }
.summary-value { margin: 12px 0 8px; color: var(--el-text-color-primary); font: 700 clamp(20px, 2vw, 29px)/1.15 var(--font-data); font-variant-numeric: tabular-nums; white-space: nowrap; }
.summary-note { min-height: 18px; color: var(--el-text-color-secondary); font-size: 12px; }
.overdue-note { color: var(--el-color-danger); font-weight: 600; }
.filter-band {
  display: grid;
  grid-template-columns: repeat(4, minmax(135px, 1fr)) minmax(260px, 1.5fr) minmax(210px, 1.3fr) auto;
  gap: 10px;
  margin-bottom: 14px;
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  background: var(--surface-solid);
}
.filter-band > :deep(.el-select), .filter-band > :deep(.el-date-editor), .filter-band > :deep(.el-input) { width: 100%; }
.filter-actions { display: flex; gap: 8px; }
.ledger-card :deep(.el-card__header) { padding: 14px 16px; }
.ledger-card :deep(.el-card__body) { padding: 0 16px 16px; }
.ledger-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.ledger-header > div { display: flex; align-items: baseline; gap: 10px; }
.ledger-header strong { font-size: 16px; }
.ledger-header span { color: var(--el-text-color-secondary); font-size: 12px; }
.amount-cell { font-family: var(--font-data); font-variant-numeric: tabular-nums; }
.ledger-card :deep(.el-pagination) { justify-content: flex-end; margin-top: 16px; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 16px; }
@media (max-width: 1380px) {
  .filter-band { grid-template-columns: repeat(3, minmax(150px, 1fr)); }
}
@media (max-width: 980px) {
  .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .filter-band { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 680px) {
  .page-heading { align-items: flex-start; flex-direction: column; }
  .summary-grid, .filter-band, .form-grid { grid-template-columns: 1fr; }
  .summary-value { white-space: normal; }
  .filter-actions { justify-content: flex-end; }
}
</style>
