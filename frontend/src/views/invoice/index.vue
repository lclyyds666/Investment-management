<template>
  <div class="invoice">
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="12" :sm="8" :md="8"><el-card shadow="hover"><div class="stat-label">待开发票</div><div class="stat-value warn">{{ stats.pending }}</div></el-card></el-col>
      <el-col :xs="12" :sm="8" :md="8"><el-card shadow="hover"><div class="stat-label">已开发票</div><div class="stat-value ok">{{ stats.issued }}</div></el-card></el-col>
      <el-col :xs="24" :sm="8" :md="8"><el-card shadow="hover"><div class="stat-label">已开发票金额（元）</div><div class="stat-value blue">{{ money(stats.issued_amount) }}</div></el-card></el-col>
    </el-row>

    <el-tabs v-model="activeDirection" @tab-change="reload">
      <el-tab-pane label="进项发票" name="input" />
      <el-tab-pane label="销项发票" name="output" />
    </el-tabs>

    <ProTable
      ref="tableRef"
      :title="activeDirection === 'input' ? '进项发票管理' : '销项发票管理'"
      :fetch="fetchRows"
      :columns="columns"
      :search-keys="['invoice_title', 'customer_name', 'contract_no', 'tax_no']"
      search-placeholder="搜索抬头 / 客户 / 合同 / 税号"
      empty-text="暂无发票数据"
      @loaded="loadStats"
    >
      <template #toolbar>
        <el-button :icon="Refresh" @click="reload">刷新</el-button>
      </template>
      <template #status="{ row }">
        <el-tag v-if="row" :type="INVOICE_STATUS_META[row.status]?.type">{{ row.status_label || INVOICE_STATUS_META[row.status]?.text || row.status }}</el-tag>
      </template>
      <template #actions="{ row }">
        <template v-if="row">
          <el-button v-if="canManage" size="small" type="primary" link :icon="Edit" @click="openEdit(row)">编辑</el-button>
          <el-button v-if="canManage" size="small" type="success" link :icon="Upload" @click="chooseFiles(row)">上传发票</el-button>
          <template v-if="row.direction === 'output'">
            <el-button size="small" link @click="openDetails(row)">明细</el-button>
            <el-button v-if="canManage && !row.workflow_instance_id" size="small" link @click="generateApproval(row)">生成审批单</el-button>
            <el-button v-if="canManage && canSubmitApproval(row)" size="small" link @click="submitApproval(row)">提交审批</el-button>
            <el-button v-if="canView" size="small" link @click="printDetails(row)">打印明细</el-button>
            <el-button v-if="canView && row.approval_status === 'approved'" size="small" link @click="printApproval(row)">打印审批单</el-button>
          </template>
        </template>
      </template>
    </ProTable>

    <el-dialog v-model="editVisible" :title="activeDirection === 'input' ? '编辑进项发票' : '编辑销项发票'" width="620px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="116px">
        <el-form-item label="发票抬头" prop="invoice_title"><el-input v-model="form.invoice_title" /></el-form-item>
        <el-form-item label="税号"><el-input v-model="form.tax_no" /></el-form-item>
        <el-form-item label="金额（元）" prop="amount"><el-input-number v-model="form.amount" :min="0" :precision="2" style="width: 100%" /></el-form-item>
        <el-form-item v-if="activeDirection === 'output'" label="关联合同" prop="contract_no">
          <el-select v-model="form.contract_no" filterable clearable style="width: 100%" @change="onContractChange">
            <el-option v-for="contract in contracts" :key="contract.id || contract.contract_no" :label="`${contract.contract_no || ''} ${contract.title || ''}`" :value="contract.contract_no" />
          </el-select>
        </el-form-item>
        <template v-if="activeDirection === 'output'">
          <el-form-item label="客户名称"><el-input v-model="form.customer_name" /></el-form-item>
          <el-form-item label="客户税号"><el-input v-model="form.customer_social_credit_code" /></el-form-item>
          <el-form-item label="客户地址"><el-input v-model="form.customer_address" /></el-form-item>
          <el-form-item label="客户电话"><el-input v-model="form.customer_phone" /></el-form-item>
          <el-form-item label="开户行"><el-input v-model="form.customer_bank_name" /></el-form-item>
          <el-form-item label="银行账号"><el-input v-model="form.customer_bank_account" /></el-form-item>
        </template>
        <el-form-item label="状态"><span class="readonly-status">{{ statusText(form.status) }}（状态由附件上传自动更新）</span></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" /></el-form-item>
        <el-form-item label="发票附件">
          <el-upload multiple :auto-upload="false" :show-file-list="true" :on-change="onFileChange">
            <el-button :icon="Upload">选择多个文件</el-button>
          </el-upload>
          <div v-if="attachments.length" class="attachment-list">
            <div v-for="attachment in attachments" :key="attachment.id">{{ attachment.original_name }}</div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="销项发票明细" width="760px">
      <el-alert v-if="detailDifference !== 0" type="warning" :closable="false" show-icon>
        明细合计与发票金额差额：{{ money(detailDifference) }}，差额为 0 后才能保存、打印或生成审批单。
      </el-alert>
      <el-table :data="details" border stripe>
        <el-table-column prop="line_no" label="序号" width="70" />
        <el-table-column prop="source_kind" label="来源类型" width="110" />
        <el-table-column prop="platform" label="平台" width="130" />
        <el-table-column label="价税合计" width="110"><template #default>价税合计</template></el-table-column>
        <el-table-column prop="item_name" label="项目" min-width="160" />
        <el-table-column label="金额（元）" width="150"><template #default="scope"><el-input-number v-model="scope.row.amount" :min="0" :precision="2" /></template></el-table-column>
        <el-table-column label="操作" width="90"><template #default="scope"><el-button v-if="canManage" size="small" link @click="saveDetail(scope.row)">保存</el-button></template></el-table-column>
      </el-table>
      <div class="detail-summary"><span class="detail-tax-label">价税合计</span>　发票金额：{{ money(detailInvoiceAmount) }}　明细合计：{{ money(detailTotal) }}　差额：{{ money(detailDifference) }}</div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button v-if="canView" :disabled="detailDifference !== 0" @click="printDetails(detailInvoice)">打印明细</el-button>
        <el-button v-if="canManage" :disabled="detailDifference !== 0" type="primary" @click="generateApproval(detailInvoice)">生成审批单</el-button>
        <el-button v-if="canManage && canSubmitApproval(detailInvoice)" :disabled="detailDifference !== 0" @click="submitApproval(detailInvoice)">提交审批</el-button>
      </template>
    </el-dialog>

    <input ref="fileInput" type="file" multiple hidden @change="onNativeFiles" />
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Edit, Refresh, Upload } from '@element-plus/icons-vue'
import { usePortalStore } from '@/store/portal'
import { canUsePermission } from '@/utils/businessAuthorization'
import { INVOICE_STATUS_META } from '@/constants/business'
import { downloadBlob } from '@/utils/file'
import {
  listInvoices, invoiceStats, updateInvoice,
  listInvoiceAttachments, uploadInvoiceAttachments, listInvoiceDetails,
  updateInvoiceDetail, createInvoiceApprovalForm, submitInvoiceApproval, downloadInvoiceDocument
} from '@/api/invoice'
import { listContracts } from '@/api/contract'
import { getCustomer, listCustomers } from '@/api/customer'
import ProTable from '@/components/ProTable.vue'

const portalStore = usePortalStore()
const canView = computed(() => canUsePermission(portalStore, 'supply.invoice.view'))
const canManage = computed(() => canUsePermission(portalStore, 'supply.invoice.manage'))
const activeDirection = ref('input')
const tableRef = ref()
const stats = ref({ pending: 0, issued: 0, issued_amount: 0 })
const contracts = ref([])
const customers = ref([])
const attachments = ref([])
const pendingFiles = ref([])
const fileInput = ref()
const selectedUploadRow = ref(null)

const columns = [
  { prop: 'invoice_title', label: '发票抬头', minWidth: 190, showOverflowTooltip: true },
  { prop: 'tax_no', label: '税号', width: 180 },
  { label: '金额（元）', width: 130, align: 'right', formatter: row => money(row.amount) },
  { prop: 'contract_no', label: '关联合同', width: 150, showOverflowTooltip: true },
  { label: '状态', width: 110, align: 'center', slot: 'status' },
  { label: '操作', minWidth: 300, align: 'center', fixed: 'right', slot: 'actions' }
]

const fetchRows = () => listInvoices({ direction: activeDirection.value })
const reload = () => tableRef.value?.reload?.()
async function loadStats() {
  try { stats.value = await invoiceStats() } catch { /* request interceptor handles message */ }
}
function money(value) { return Number(value || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }
function statusText(status) { return INVOICE_STATUS_META[status]?.text || status || '未知' }
const editVisible = ref(false)
const saving = ref(false)
const editingId = ref(null)
const editingScenicId = ref('global')
const formRef = ref()
const form = reactive({
  invoice_title: '', tax_no: '', amount: 0, contract_no: '', customer_name: '',
  customer_social_credit_code: '', customer_address: '', customer_phone: '',
  customer_bank_name: '', customer_bank_account: '', status: 'pending', remark: ''
})
const rules = {
  invoice_title: [{ required: true, message: '请输入发票抬头', trigger: 'blur' }],
  amount: [{ required: true, message: '请输入金额', trigger: 'blur' }]
}
function resetForm(row) {
  Object.assign(form, {
    invoice_title: row.invoice_title || '', tax_no: row.tax_no || '', amount: Number(row.amount || 0),
    contract_no: row.contract_no || '', customer_name: row.customer_name || '',
    customer_social_credit_code: row.customer_social_credit_code || '', customer_address: row.customer_address || '',
    customer_phone: row.customer_phone || '', customer_bank_name: row.customer_bank_name || '',
    customer_bank_account: row.customer_bank_account || '', status: row.status || 'pending', remark: row.remark || ''
  })
}
function openEdit(row) {
  activeDirection.value = row.direction || activeDirection.value
  editingId.value = row.id
  editingScenicId.value = row.scenic_id || row.scenicId || 'global'
  resetForm(row)
  pendingFiles.value = []
  attachments.value = []
  editVisible.value = true
  if (activeDirection.value === 'output') loadOutputReferences(row)
  if (activeDirection.value === 'input') loadAttachments(row.id)
}
function contractMemoryKey(row = {}) {
  const scenicId = row.scenic_id || row.scenicId || editingScenicId.value || 'global'
  return `invoice-contract-default:${scenicId}:${activeDirection.value}`
}
function contractForNumber(contractNo) {
  return contracts.value.find(contract => contract.contract_no === contractNo)
}
function customerForContract(contract) {
  if (!contract) return null
  const creditCode = contract.customer_credit_code || contract.customer_social_credit_code || ''
  const customerName = contract.customer_name || contract.party_b || ''
  return customers.value.find(customer =>
    (creditCode && (customer.social_credit_code === creditCode || customer.customer_credit_code === creditCode))
      || (customerName && customer.name === customerName)
  ) || null
}
function applyContractCustomer(contract) {
  const customer = customerForContract(contract)
  const snapshot = customer || contract || {}
  form.customer_name = snapshot.name || snapshot.customer_name || form.customer_name || ''
  form.customer_social_credit_code = snapshot.social_credit_code || snapshot.customer_credit_code || snapshot.customer_social_credit_code || form.customer_social_credit_code || ''
  form.customer_address = snapshot.address || snapshot.customer_address || form.customer_address || ''
  form.customer_phone = snapshot.phone || snapshot.customer_phone || form.customer_phone || ''
  form.customer_bank_name = snapshot.bank_name || snapshot.customer_bank_name || form.customer_bank_name || ''
  form.customer_bank_account = snapshot.bank_account || snapshot.customer_bank_account || form.customer_bank_account || ''
}
function onContractChange(contractNo) {
  const contract = contractForNumber(contractNo)
  if (contract) applyContractCustomer(contract)
}
async function loadOutputReferences(row) {
  try {
    const [contractData, customerData] = await Promise.all([listContracts(), listCustomers()])
    contracts.value = Array.isArray(contractData) ? contractData : (contractData?.items || [])
    customers.value = Array.isArray(customerData) ? customerData : (customerData?.items || [])
    if (!form.contract_no) {
      const remembered = localStorage.getItem(contractMemoryKey(row))
      if (remembered) form.contract_no = remembered
    }
    if (form.contract_no) {
      const selectedContract = contractForNumber(form.contract_no)
      if (selectedContract?.customer_id) {
        try {
          const customer = await getCustomer(selectedContract.customer_id)
          if (customer) customers.value = [customer, ...customers.value.filter(item => item.id !== customer.id)]
        } catch { /* fall back to the list snapshot */ }
      }
      onContractChange(form.contract_no)
    }
  } catch {
    contracts.value = []
    customers.value = []
  }
}
async function loadAttachments(id) {
  try { attachments.value = await listInvoiceAttachments(id) } catch { attachments.value = [] }
}
function chooseFiles(row) { selectedUploadRow.value = row; fileInput.value?.click() }
function onFileChange(upload) { if (upload?.raw) pendingFiles.value.push(upload.raw) }
function onNativeFiles(event) {
  const files = Array.from(event.target.files || [])
  if (selectedUploadRow.value) uploadFiles(selectedUploadRow.value, files)
  event.target.value = ''
}
async function uploadFiles(row, files) {
  const selected = files?.map(item => item?.raw || item).filter(Boolean) || []
  if (!selected.length) return
  await uploadInvoiceAttachments(row.id, selected)
  pendingFiles.value = []
  ElMessage.success('发票附件上传成功，状态已更新为已开发票')
  reload(); await loadStats()
}
async function saveEdit() {
  await formRef.value?.validate?.()
  saving.value = true
  try {
    const payload = { ...form }
    delete payload.status
    await updateInvoice(editingId.value, payload)
    if (pendingFiles.value.length) await uploadFiles({ id: editingId.value }, pendingFiles.value)
    if (activeDirection.value === 'output' && form.contract_no) localStorage.setItem(contractMemoryKey(), form.contract_no)
    ElMessage.success('保存成功')
    editVisible.value = false
    reload()
  } finally { saving.value = false }
}

const detailVisible = ref(false)
const detailInvoice = ref(null)
const details = ref([])
const detailTotal = ref(0)
const detailDifference = ref(0)
const detailInvoiceAmount = computed(() => Number(detailInvoice.value?.amount || 0))
const canPrintDetails = computed(() => canView.value && detailDifference.value === 0)
const balancedCheckLoading = ref(false)
async function ensureDetailsBalanced(invoiceId) {
  if (!invoiceId) return false
  balancedCheckLoading.value = true
  try {
    const result = await listInvoiceDetails(invoiceId)
    const difference = Number(result?.difference || 0)
    if (detailInvoice.value?.id === invoiceId) {
      details.value = result?.items || details.value
      detailTotal.value = Number(result?.detail_total || 0)
      detailDifference.value = difference
    }
    if (difference !== 0) ElMessage.warning('发票明细金额未平衡，暂不能执行该操作')
    return difference === 0
  } catch {
    return false
  } finally {
    balancedCheckLoading.value = false
  }
}
async function openDetails(row) {
  detailInvoice.value = row
  detailVisible.value = true
  const result = await listInvoiceDetails(row.id)
  details.value = result?.items || []
  detailTotal.value = Number(result?.detail_total || 0)
  detailDifference.value = Number(result?.difference || 0)
}
async function saveDetail(row) {
  const result = await updateInvoiceDetail(detailInvoice.value.id, row.id, { amount: row.amount, platform: row.platform, item_name: row.item_name })
  details.value = result?.items || details.value
  detailTotal.value = Number(result?.detail_total || 0)
  detailDifference.value = Number(result?.difference || 0)
}
async function generateApproval(row) {
  if (!canManage.value || !row?.id || !(await ensureDetailsBalanced(row.id))) return
  await createInvoiceApprovalForm(row.id)
  ElMessage.success('审批单已生成')
  reload()
}
function canPrintApproval(row) { return canView.value && row?.approval_status === 'approved' }
function canSubmitApproval(row) {
  return canManage.value && ['draft', 'rejected'].includes(row?.approval_status) && Boolean(row?.workflow_instance_id || row?.approval_status === 'draft')
}
async function submitApproval(row) {
  if (!canSubmitApproval(row)) return
  await submitInvoiceApproval(row.id)
  ElMessage.success('审批单已提交')
  reload()
}
async function printDetails(row) {
  if (!canView.value || !(await ensureDetailsBalanced(row?.id))) return
  const blob = await downloadInvoiceDocument(row.id, 'details')
  downloadBlob(blob, `开票明细_${row.id}.xlsx`)
}
async function printApproval(row) {
  if (!canPrintApproval(row)) return
  if (!(await ensureDetailsBalanced(row.id))) return
  const blob = await downloadInvoiceDocument(row.id, 'approval')
  downloadBlob(blob, `开票审批单_${row.id}.docx`)
}
</script>

<style scoped lang="scss">
.stat-row { margin-bottom: 12px; }
.stat-label { color: var(--el-text-color-secondary); font-size: 14px; }
.stat-value { margin-top: 8px; font-size: 30px; font-weight: 800; color: var(--el-text-color-primary); }
.stat-value.warn { color: var(--el-color-warning); }
.stat-value.ok { color: var(--el-color-success); }
.stat-value.blue { color: var(--el-color-primary); }
.readonly-status { color: var(--el-text-color-secondary); }
.detail-summary { margin-top: 14px; text-align: right; color: var(--el-text-color-secondary); }
@media (max-width: 768px) { .stat-row .el-col { margin-bottom: 12px; } }
</style>
