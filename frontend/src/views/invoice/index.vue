<template>
  <div class="invoice" v-loading="loading">
    <!-- 统计卡 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6"><el-card shadow="hover"><div class="stat-label">发票总数</div><div class="stat-value">{{ stats.total }}</div></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><div class="stat-label">待开票</div><div class="stat-value warn">{{ stats.pending }}</div></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><div class="stat-label">已开票</div><div class="stat-value ok">{{ stats.issued }}</div></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><div class="stat-label">已开票金额(元)</div><div class="stat-value blue">{{ Number(stats.issued_amount || 0).toLocaleString() }}</div></el-card></el-col>
    </el-row>

    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>发票 / 开票管理</span>
          <div>
            <el-button type="primary" :icon="Plus" @click="openCreate">新建发票</el-button>
            <el-button :icon="Refresh" @click="load">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="list" border stripe>
        <el-table-column prop="invoice_title" label="发票抬头" min-width="200" show-overflow-tooltip />
        <el-table-column prop="tax_no" label="税号" width="180" />
        <el-table-column prop="invoice_type" label="类型" width="150" />
        <el-table-column label="金额(元)" width="130" align="right">
          <template #default="{ row }">{{ Number(row.amount).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="contract_no" label="关联合同" width="130" />
        <el-table-column label="开票状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="INVOICE_STATUS_META[row.status]?.type">{{ row.status_label }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240" align="center">
          <template #default="{ row }">
            <el-button v-if="row.status === 'pending'" size="small" type="success" link @click="issue(row)">
              确认开票
            </el-button>
            <el-button size="small" type="primary" plain :icon="Edit" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" plain :icon="Delete" @click="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>暂无发票数据</template>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑发票' : '新建发票'" width="560px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="96px">
        <el-form-item label="发票抬头" prop="invoice_title"><el-input v-model="form.invoice_title" /></el-form-item>
        <el-form-item label="纳税人识别号"><el-input v-model="form.tax_no" placeholder="税号" /></el-form-item>
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
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Edit, Delete } from '@element-plus/icons-vue'
import { INVOICE_STATUS_META } from '@/constants/business'
import { listInvoices, invoiceStats, createInvoice, updateInvoice, deleteInvoice } from '@/api/invoice'

const loading = ref(false)
const list = ref([])
const stats = ref({ total: 0, pending: 0, issued: 0, void: 0, issued_amount: 0, pending_amount: 0 })

async function load() {
  loading.value = true
  try {
    list.value = await listInvoices()
    stats.value = await invoiceStats()
  } finally { loading.value = false }
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
  amount: [{ required: true, message: '请输入金额', trigger: 'blur' }]
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
    dialogVisible.value = false; load()
  } finally { saving.value = false }
}
async function issue(row) {
  const today = new Date().toISOString().slice(0, 10)
  await updateInvoice(row.id, { status: 'issued', issued_date: today })
  ElMessage.success('已确认开票'); load()
}
async function onDelete(row) {
  try { await ElMessageBox.confirm(`确定删除发票「${row.invoice_title}」吗？`, '删除确认', { type: 'warning' }) }
  catch { return }
  await deleteInvoice(row.id); ElMessage.success('删除成功'); load()
}

onMounted(load)
</script>

<style scoped lang="scss">
.stat-row { margin-bottom: 16px; }
.stat-label { color: #909399; font-size: 14px; }
.stat-value { margin-top: 8px; font-size: 26px; font-weight: 700; color: #1f2937; }
.stat-value.warn { color: #e6a23c; }
.stat-value.ok { color: #67c23a; }
.stat-value.blue { color: #409eff; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
</style>
