<template>
  <div class="invoice">
    <!-- 统计卡(响应式:窄屏两列、超窄单列) -->
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="12" :sm="8" :md="8"><el-card shadow="hover"><div class="stat-label">待开票</div><div class="stat-value warn">{{ stats.pending }}</div></el-card></el-col>
      <el-col :xs="12" :sm="8" :md="8"><el-card shadow="hover"><div class="stat-label">已开票</div><div class="stat-value ok">{{ stats.issued }}</div></el-card></el-col>
      <el-col :xs="24" :sm="8" :md="8"><el-card shadow="hover"><div class="stat-label">已开票金额(元)</div><div class="stat-value blue">{{ Number(stats.issued_amount || 0).toLocaleString() }}</div></el-card></el-col>
    </el-row>

    <ProTable
      ref="tableRef"
      title="发票 / 开票管理"
      :fetch="listInvoices"
      :columns="columns"
      :search-keys="['invoice_title', 'customer_name', 'contract_no', 'tax_no']"
      search-placeholder="搜索抬头 / 客户 / 合同 / 税号"
      empty-text="暂无发票数据"
      @loaded="loadStats"
    >
      <template #toolbar>
        <el-button type="primary" :icon="Plus" @click="openCreate">新建发票</el-button>
        <el-button :icon="Refresh" @click="reload">刷新</el-button>
      </template>

      <template #status="{ row }">
        <el-tag :type="INVOICE_STATUS_META[row.status]?.type">{{ row.status_label }}</el-tag>
      </template>

      <template #actions="{ row }">
        <el-button v-if="row.status === 'pending'" size="small" type="success" link @click="issue(row)">
          确认开票
        </el-button>
        <el-button size="small" type="primary" plain :icon="Edit" @click="openEdit(row)">编辑</el-button>
        <el-button size="small" type="danger" plain :icon="Delete" @click="onDelete(row)">删除</el-button>
      </template>
    </ProTable>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑发票' : '新建发票'" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-form-item label="发票抬头" prop="invoice_title"><el-input v-model="form.invoice_title" /></el-form-item>
        <el-form-item label="纳税人识别号" prop="tax_no"><el-input v-model="form.tax_no" placeholder="15/17/18/20 位纳税人识别号" /></el-form-item>
        <el-form-item label="发票类型">
          <el-select v-model="form.invoice_type" style="width: 100%">
            <el-option label="增值税专用发票" value="增值税专用发票" />
            <el-option label="增值税普通发票" value="增值税普通发票" />
            <el-option label="电子发票" value="电子发票" />
          </el-select>
        </el-form-item>
        <el-form-item label="金额(元)" prop="amount">
          <el-input-number v-model="form.amount" :min="0" :step="10000" style="width: 100%" />
        </el-form-item>
        <el-form-item label="客户名称"><el-input v-model="form.customer_name" /></el-form-item>
        <el-form-item label="关联合同"><el-input v-model="form.contract_no" placeholder="如 HT-2026-001" /></el-form-item>
        <el-form-item label="开票状态">
          <el-select v-model="form.status" style="width: 100%">
            <el-option label="待开票" value="pending" />
            <el-option label="已开票" value="issued" />
            <el-option label="已作废" value="void" />
          </el-select>
        </el-form-item>
        <el-form-item label="开票日期">
          <el-date-picker v-model="form.issued_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Edit, Delete } from '@element-plus/icons-vue'
import { INVOICE_STATUS_META } from '@/constants/business'
import { listInvoices, invoiceStats, createInvoice, updateInvoice, deleteInvoice } from '@/api/invoice'
import ProTable from '@/components/ProTable.vue'

// 列配置:交给 ProTable 渲染;slot 列(状态/操作)在模板里具名插槽实现
const columns = [
  { prop: 'invoice_title', label: '发票抬头', minWidth: 200, showOverflowTooltip: true },
  { prop: 'tax_no', label: '税号', width: 180 },
  { prop: 'invoice_type', label: '类型', width: 150 },
  { label: '金额(元)', width: 130, align: 'right', formatter: (row) => Number(row.amount).toLocaleString() },
  { prop: 'contract_no', label: '关联合同', width: 130 },
  { label: '开票状态', width: 110, align: 'center', slot: 'status' },
  { label: '操作', width: 240, align: 'center', fixed: 'right', slot: 'actions' }
]

const tableRef = ref()
const reload = () => tableRef.value?.reload()

// 统计卡:独立于列表,列表加载完成(@loaded)后同步刷新
const stats = ref({ total: 0, pending: 0, issued: 0, void: 0, issued_amount: 0, pending_amount: 0 })
async function loadStats() {
  try { stats.value = await invoiceStats() } catch { /* 错误已由拦截器提示 */ }
}

const dialogVisible = ref(false)
const saving = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const formRef = ref()
const emptyForm = () => ({
  invoice_title: '', tax_no: '', invoice_type: '增值税专用发票', amount: 0,
  customer_name: '', contract_no: '', status: 'pending', issued_date: null, remark: ''
})
const form = reactive(emptyForm())
const rules = {
  invoice_title: [{ required: true, message: '请输入发票抬头', trigger: 'blur' }],
  amount: [{ required: true, message: '请输入金额', trigger: 'blur' }],
  tax_no: [{ pattern: /^[A-Z0-9]{15,20}$/, message: '纳税人识别号为 15-20 位大写字母或数字', trigger: 'blur' }]
}
function openCreate() {
  isEdit.value = false; editingId.value = null
  Object.assign(form, emptyForm()); formRef.value?.clearValidate?.(); dialogVisible.value = true
}
function openEdit(row) {
  isEdit.value = true; editingId.value = row.id
  Object.assign(form, {
    invoice_title: row.invoice_title, tax_no: row.tax_no, invoice_type: row.invoice_type,
    amount: Number(row.amount), customer_name: row.customer_name, contract_no: row.contract_no,
    status: row.status, issued_date: row.issued_date || null, remark: row.remark
  })
  formRef.value?.clearValidate?.(); dialogVisible.value = true
}
async function onSave() {
  await formRef.value?.validate()
  saving.value = true
  try {
    if (isEdit.value) { await updateInvoice(editingId.value, { ...form }); ElMessage.success('修改成功') }
    else { await createInvoice({ ...form }); ElMessage.success('创建成功') }
    dialogVisible.value = false; reload()
  } finally { saving.value = false }
}
async function issue(row) {
  const today = new Date().toISOString().slice(0, 10)
  await updateInvoice(row.id, { status: 'issued', issued_date: today })
  ElMessage.success('已确认开票'); reload()
}
async function onDelete(row) {
  try { await ElMessageBox.confirm(`确定删除发票「${row.invoice_title}」吗？`, '删除确认', { type: 'warning' }) }
  catch { return }
  await deleteInvoice(row.id); ElMessage.success('删除成功'); reload()
}
</script>

<style scoped lang="scss">
.stat-row { margin-bottom: 16px; }
.stat-label { color: var(--el-text-color-secondary); font-size: 14px; }
.stat-value { margin-top: 8px; font-size: 26px; font-weight: 700; color: var(--el-text-color-primary); }
.stat-value.warn { color: #e6a23c; }
.stat-value.ok { color: #67c23a; }
.stat-value.blue { color: #409eff; }
/* 窄屏统计卡之间留出竖向间距 */
@media (max-width: 768px) {
  .stat-row .el-col { margin-bottom: 12px; }
}
</style>
