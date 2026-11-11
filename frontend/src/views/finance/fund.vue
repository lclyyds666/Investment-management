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

    <div class="finance-tabs">
      <el-button :type="activeTab === 'ledger' ? 'primary' : 'default'" @click="activeTab = 'ledger'">资金流水</el-button>
      <el-button :type="activeTab === 'execution' ? 'primary' : 'default'" @click="activeTab = 'execution'">待资金执行</el-button>
    </div>

    <el-card v-if="activeTab === 'ledger'" shadow="never" class="ledger-card">
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
        <el-table-column label="已核销（元）" width="140" align="right">
          <template #default="{ row }">{{ formatReconciliationAmount(row.allocated_amount) }}</template>
        </el-table-column>
        <el-table-column label="可核销（元）" width="140" align="right">
          <template #default="{ row }">{{ formatReconciliationAmount(row.unallocated_amount) }}</template>
        </el-table-column>
        <el-table-column prop="counterparty" label="对方单位" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.counterparty || '—' }}</template>
        </el-table-column>
        <el-table-column prop="summary" label="用途 / 摘要" min-width="190" show-overflow-tooltip>
          <template #default="{ row }">{{ row.summary || '—' }}</template>
        </el-table-column>
        <el-table-column label="来源" min-width="140">
          <template #default="{ row }">{{ taskSource(row) }}</template>
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
            <el-button v-if="!row.execution_task_id && ['business_payment', 'customer_payment'].includes(row.category)" link type="primary" @click="openAssociation(row)">历史关联</el-button>
            <el-button link type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="canSettle(row)" link type="success" :icon="CircleCheck" @click="onSettle(row)">结清</el-button>
            <el-button v-if="!row.execution_task_id" link type="danger" :icon="Delete" @click="onDelete(row)">删除</el-button>
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

    <el-card v-else shadow="never" class="ledger-card">
      <template #header><div class="ledger-header"><strong>待资金执行</strong><el-button :icon="Refresh" :loading="executionLoading" @click="loadExecutionTasks">刷新</el-button></div></template>
      <el-table v-loading="executionLoading" :data="executionTasks" stripe empty-text="暂无待执行任务">
        <el-table-column prop="id" label="任务" width="75" />
        <el-table-column prop="scenic_id" label="景区" width="120" />
        <el-table-column label="方向" width="90"><template #default="{ row }">{{ row.direction === 'outflow' ? '支出' : '收入' }}</template></el-table-column>
        <el-table-column label="计划金额" width="130"><template #default="{ row }">{{ formatAmount(row.planned_amount) }}</template></el-table-column>
        <el-table-column label="已执行" width="130"><template #default="{ row }">{{ formatAmount(row.executed_amount) }}</template></el-table-column>
        <el-table-column label="未执行" width="130"><template #default="{ row }">{{ formatAmount(Number(row.planned_amount) - Number(row.executed_amount)) }}</template></el-table-column>
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column label="操作" width="110"><template #default="{ row }"><el-button link type="primary" :disabled="row.status === 'completed' || row.status === 'cancelled'" @click="openExecution(row)">执行</el-button></template></el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="associationVisible" title="历史资金关联" width="520px">
      <el-alert title="逐笔核实后关联已审批合同；付款可补充同合同、同景区的已审批付款单。金额和发生日期保持原记录。" type="info" :closable="false" />
      <el-form label-width="120px">
        <el-form-item label="已审批合同"><el-select v-model="associationForm.contract_id" filterable placeholder="选择有权访问的合同"><el-option v-for="item in associationContracts" :key="item.id" :value="item.id" :label="`${item.contract_no} · ${item.title} · ${item.scenic_id}`" /></el-select></el-form-item>
        <el-form-item v-if="associationRow?.direction === 'usage'" label="付款审批单 ID"><el-input-number v-model="associationForm.approval_form_id" :min="1" :precision="0" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="associationVisible = false">取消</el-button><el-button type="primary" :loading="associationSaving" @click="submitAssociation">核实并关联</el-button></template>
    </el-dialog>

    <el-dialog v-model="executionDialogVisible" title="财务执行" width="560px">
      <el-form label-width="110px">
        <el-form-item label="实际日期"><el-date-picker v-model="executionForm.occurred_on" type="date" value-format="YYYY-MM-DD" /></el-form-item>
        <el-form-item label="执行金额（万元）"><el-input-number v-model="executionForm.amount" :min="0.000001" :precision="6" /></el-form-item>
        <el-form-item label="对方单位"><el-input v-model="executionForm.counterparty" /></el-form-item>
        <el-form-item label="银行流水号"><el-input v-model="executionForm.bank_reference" /></el-form-item>
        <el-form-item label="摘要"><el-input v-model="executionForm.summary" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="executionForm.remark" type="textarea" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="executionDialogVisible = false">取消</el-button><el-button type="primary" @click="submitExecution">确认执行</el-button></template>
    </el-dialog>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑资金流水' : '新增资金流水'" width="680px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="104px">
        <div class="form-grid">
          <el-form-item label="资金方向" prop="direction">
            <el-radio-group v-model="form.direction" :disabled="editingSettled || editingExecution" @change="onFormDirectionChange">
              <el-radio-button value="increase">资金增加</el-radio-button>
              <el-radio-button value="usage">资金使用</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="资金类型" prop="category">
            <el-select v-model="form.category" :disabled="editingSettled || editingExecution" placeholder="请选择类型" style="width: 100%">
              <el-option v-for="item in formCategoryOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="金额（万元）" prop="amountWan">
            <el-input-number v-model="form.amountWan" :disabled="editingExecution" :min="0.000001" :precision="6" :step="1" controls-position="right" style="width: 100%" />
          </el-form-item>
          <el-form-item label="发生日期" prop="occurred_on">
            <el-date-picker v-model="form.occurred_on" :disabled="editingExecution" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
          <el-form-item label="到期日期" :required="requiresMaturity">
            <el-date-picker v-model="form.maturity_date" :disabled="editingExecution" type="date" value-format="YYYY-MM-DD" clearable style="width: 100%" />
          </el-form-item>
          <el-form-item label="对方单位" prop="counterparty">
            <el-input v-model="form.counterparty" :disabled="editingExecution" maxlength="200" placeholder="银行、公司或客户名称" />
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { CircleCheck, Delete, Edit, Plus, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createFund,
  associateLegacyFund,
  listLegacyFundContracts,
  deleteFund,
  getFundSummary,
  listCashExecutionTasks,
  listFunds,
  executeCashTask,
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
const route = useRoute()
const maturityStatuses = new Set(['due_soon', 'overdue', 'normal', 'settled'])
const routeMaturityStatus = () => maturityStatuses.has(String(route.query.maturity_status || ''))
  ? String(route.query.maturity_status)
  : ''
const canWrite = computed(() => canUsePermission(portalStore, 'supply.finance.update'))
const loading = ref(false)
const summaryLoading = ref(false)
const activeTab = ref(route.query.tab === 'execution' ? 'execution' : 'ledger')
const executionLoading = ref(false)
const executionTasks = ref([])
const executionDialogVisible = ref(false)
const executionTask = ref(null)
const executionForm = reactive({ amount: null, occurred_on: todayString(), counterparty: '', bank_reference: '', summary: '', remark: '' })
const saving = ref(false)
const dialogVisible = ref(false)
const editingId = ref(null)
const editingSettled = ref(false)
const editingExecution = ref(false)
const associationVisible = ref(false)
const associationSaving = ref(false)
const associationRow = ref(null)
const associationContracts = ref([])
const associationForm = reactive({ contract_id: null, approval_form_id: null })

async function openAssociation(row) {
  if (!canWrite.value || row.execution_task_id) return
  associationRow.value = row
  associationContracts.value = (await listLegacyFundContracts()).filter(item => !row.scenic_id || row.scenic_id === item.scenic_id)
  Object.assign(associationForm, { contract_id: row.contract_id || null, approval_form_id: row.approval_form_id || null })
  associationVisible.value = true
}

async function submitAssociation() {
  if (!canWrite.value || !associationForm.contract_id || associationSaving.value) return
  associationSaving.value = true
  try {
    await associateLegacyFund(associationRow.value.id, { ...associationForm })
    associationVisible.value = false
    ElMessage.success('历史资金关联已保存')
    await loadLedger()
  } finally {
    associationSaving.value = false
  }
}
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
  maturity_status: routeMaturityStatus(),
  dateRange: [],
  keyword: '',
  page: 1,
  page_size: 20
})

watch(
  () => route.query.maturity_status,
  async () => {
    const nextStatus = routeMaturityStatus()
    if (nextStatus === filters.maturity_status) return
    filters.maturity_status = nextStatus
    filters.page = 1
    await loadLedger()
  }
)

function todayString() {
  const today = new Date()
  const month = String(today.getMonth() + 1).padStart(2, '0')
  const day = String(today.getDate()).padStart(2, '0')
  return `${today.getFullYear()}-${month}-${day}`
}

function emptyForm() {
  return {
    direction: 'increase',
    category: 'own_funds',
    amountWan: null,
    occurred_on: todayString(),
    counterparty: '',
    summary: '',
    maturity_date: null,
    remark: '',
    bank_reference: ''
  }
}

const form = reactive(emptyForm())

async function loadExecutionTasks() {
  executionLoading.value = true
  try {
    const tasks = await listCashExecutionTasks({ direction: filters.direction || '' })
    executionTasks.value = route.query.task_id ? tasks.filter(task => String(task.id) === String(route.query.task_id)) : tasks
  } finally {
    executionLoading.value = false
  }
}

function openExecution(task) {
  executionTask.value = task
  Object.assign(executionForm, { amount: null, occurred_on: todayString(), counterparty: '', bank_reference: '', summary: '', remark: '' })
  executionDialogVisible.value = true
}

async function submitExecution() {
  if (!executionTask.value || !executionForm.amount) return
  await executeCashTask(executionTask.value.id, { ...executionForm, amount: wanToYuan(executionForm.amount) })
  executionDialogVisible.value = false
  await Promise.all([loadExecutionTasks(), loadLedger(), loadSummary()])
}

function taskSource(row) {
  if (!row.execution_task_id && !['customer_payment', 'business_payment'].includes(row.category)) return '手工流水'
  if (!row.execution_task_id) return row.contract_id ? `历史关联：合同 #${row.contract_id}${row.approval_form_id ? ' / 付款审批 #' + row.approval_form_id : ''}` : '历史未关联'
  return row.approval_form_id ? '付款审批 #' + row.approval_form_id : '销项发票 #' + row.invoice_id
}
const formCategoryOptions = computed(() => (CATEGORY_OPTIONS[form.direction] || []).filter(item =>
  !['customer_payment', 'business_payment'].includes(item.value) || (editingId.value && item.value === lockedClassification.category)))
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

function formatReconciliationAmount(value) {
  return Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
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
    page_size: filters.page_size,
    fund_id: route.query.fund_id,
    unallocated_only: route.query.unallocated_only === 'true'
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
  const allowed = formCategoryOptions.value
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
  editingExecution.value = false
  Object.assign(lockedClassification, { direction: '', category: '' })
  Object.assign(form, emptyForm())
  formRef.value?.clearValidate?.()
  dialogVisible.value = true
}

function openEdit(row) {
  if (!canWrite.value) return
  editingId.value = row.id
  editingExecution.value = Boolean(row.execution_task_id)
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
    remark: row.remark || '',
    bank_reference: row.bank_reference || ''
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
    counterparty: editingExecution.value ? form.counterparty : (form.counterparty?.trim() || ''),
    summary: form.summary?.trim() || '',
    maturity_date: form.maturity_date || null,
    remark: form.remark?.trim() || '',
    bank_reference: form.bank_reference || ''
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

watch(() => [route.query.task_id, route.query.fund_id, route.query.tab, route.query.unallocated_only], () => {
  activeTab.value = route.query.tab === 'execution' ? 'execution' : 'ledger'
  filters.page = 1
  void Promise.all([loadLedger(), loadExecutionTasks()]).catch(() => undefined)
})
onMounted(() => Promise.all([loadLedger(), loadSummary(), loadExecutionTasks()]))
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
