<template>
  <div class="approval" v-loading="loading">
    <el-card shadow="never">
      <template #header>
        <div class="card-header"><span>业务审批</span></div>
      </template>

      <!-- 工具栏 -->
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索客户 / 业务类型 / 合同编号" clearable class="search-input">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <div class="toolbar-right">
          <!-- 新建审批：悬停展开下拉，选择审批单类型 -->
          <el-dropdown
            v-if="isBusinessHandler"
            class="new-approval-dropdown"
            trigger="hover"
            @command="openCreate"
          >
            <el-button type="primary" :icon="Plus">
              新建审批<el-icon class="el-icon--right"><ArrowDown /></el-icon>
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="payment" :icon="Money">业务付款审批单</el-dropdown-item>
                <el-dropdown-item command="business" :icon="Document">业务审批单</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button :icon="Refresh" @click="load">刷新</el-button>
        </div>
      </div>

      <!-- 列表：统一展示 申请日期 / 客户名称 / 业务类型 / 合同编号 / 付款金额（业务审批单该列留空） -->
      <el-table :data="filteredList" border stripe>
        <el-table-column label="单据类型" width="130" align="center">
          <template #default="{ row }">
            <el-tag :type="row.form_type === 'payment' ? 'warning' : 'primary'" effect="plain">
              {{ row.form_type_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="apply_date" label="申请日期" width="120" align="center">
          <template #default="{ row }">{{ row.apply_date || '—' }}</template>
        </el-table-column>
        <el-table-column prop="customer_name" label="客户名称" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.customer_name || '—' }}</template>
        </el-table-column>
        <el-table-column prop="business_type" label="业务类型" min-width="120" show-overflow-tooltip>
          <template #default="{ row }">{{ row.business_type || '—' }}</template>
        </el-table-column>
        <el-table-column prop="contract_no" label="合同编号" width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.contract_no || '—' }}</template>
        </el-table-column>
        <el-table-column label="付款金额(元)" width="140" align="right">
          <template #default="{ row }">
            <span v-if="row.form_type === 'payment'">{{ Number(row.amount).toLocaleString() }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态 / 当前环节" width="160" align="center">
          <template #default="{ row }">
            <el-tag :type="STATUS_META[row.status]?.type">{{ row.status_label }}</el-tag>
            <div v-if="row.current_role_label" class="cur-role">→ {{ row.current_role_label }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="360" align="center">
          <template #default="{ row }">
            <div class="op-cell">
              <el-button size="small" type="info" :icon="View" @click="openDetail(row)">详情</el-button>
              <el-button size="small" color="#626aef" :icon="MagicStick" @click="openProofread(row)">AI 合同校对</el-button>
              <template v-if="row.attachment_name">
                <el-button size="small" type="primary" plain :icon="View" @click="previewFormAttachment(row)">预览附件</el-button>
                <el-button size="small" type="primary" plain :icon="Download" @click="downloadFormAttachment(row)">下载附件</el-button>
              </template>
              <el-button size="small" :icon="Printer" @click="onPrint(row)">打印导出</el-button>
              <template v-if="isBusinessHandler && ['draft', 'rejected'].includes(row.status)">
                <el-button size="small" type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
                <el-button size="small" type="success" @click="onSubmit(row)">提交审批</el-button>
                <el-button size="small" type="danger" :icon="Delete" @click="onDelete(row)">删除</el-button>
              </template>
              <template v-if="canApprove(row)">
                <el-button size="small" type="success" @click="openAction(row, 'approve')">通过</el-button>
                <el-button size="small" type="warning" @click="openAction(row, 'reject')">驳回</el-button>
              </template>
              <el-button
                v-if="row.status === 'approved' && isSuperuser"
                size="small" type="danger" :icon="Delete" @click="onDelete(row)"
              >删除</el-button>
            </div>
          </template>
        </el-table-column>
        <template #empty>暂无审批单数据</template>
      </el-table>
    </el-card>

    <!-- 新建 / 编辑审批单 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="640px" top="6vh">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px" class="approval-form">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="申请部门"><el-input v-model="form.department" placeholder="如 业务一部" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="申请日期">
              <el-date-picker v-model="form.apply_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="客户名称" prop="customer_id">
              <el-select
                v-model="form.customer_id" filterable clearable placeholder="选择客户"
                style="width: 100%" @change="onCustomerChange"
              >
                <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="业务类型"><el-input v-model="form.business_type" placeholder="如 门票代理" /></el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="业务情况">
          <el-input v-model="form.business_desc" placeholder="默认：详见合同" />
        </el-form-item>
        <el-form-item label="合同编号" prop="contract_no">
          <el-input v-model="form.contract_no" placeholder="如 HT-2026-010（AI 校对将据此匹配合同管理记录）" />
        </el-form-item>

        <!-- 付款审批单专有字段 -->
        <template v-if="form.form_type === 'payment'">
          <el-form-item label="付款金额" prop="amount">
            <el-input-number v-model="form.amount" :min="0" :step="10000" :precision="2" style="width: 100%" />
          </el-form-item>
          <el-form-item label="金额大写">
            <el-input :model-value="amountWordsPreview" readonly placeholder="根据付款金额自动生成" />
          </el-form-item>
          <el-row :gutter="12">
            <el-col :span="12">
              <el-form-item label="开户行"><el-input v-model="form.bank_name" placeholder="如 工商银行济南分行" /></el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="银行账号"><el-input v-model="form.bank_account" placeholder="收款银行账号" /></el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
        </template>

        <el-form-item label="合同附件">
          <el-upload
            class="upload-mock" drag action="#" :auto-upload="false" :show-file-list="false" :limit="1"
            accept=".pdf" :on-change="onFileChange"
            :on-exceed="() => ElMessage.warning('仅可上传一个附件')"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">点击或拖拽文件到此处<em>上传合同附件</em></div>
            <template #tip>
              <div class="upload-tip">
                仅支持 PDF，单个 ≤ 20MB
                <span v-if="pickedFile" class="picked">已选择：{{ pickedFile.name }}</span>
                <span v-else-if="form.attachment_name" class="picked">当前附件：{{ form.attachment_name }}</span>
              </div>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 通过 / 驳回 -->
    <el-dialog
      v-model="actionVisible"
      :title="action === 'approve' ? '审批通过 - 审批意见' : '驳回 - 请输入驳回原因'"
      width="480px"
    >
      <el-alert
        v-if="action === 'approve'" type="success" :closable="false" show-icon
        title="通过后将自动附加您的电子签名，并流转至下一审批环节" class="mb"
      />
      <el-form ref="actionFormRef" :model="actionForm" :rules="actionRules">
        <el-form-item prop="comment">
          <el-input
            v-model="actionForm.comment" type="textarea" :rows="4"
            :placeholder="action === 'approve' ? '请输入审批意见（可选）' : '请输入驳回原因（必填）'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="actionVisible = false">取消</el-button>
        <el-button
          :type="action === 'approve' ? 'success' : 'danger'"
          :loading="actionSaving" @click="confirmAction"
        >确认{{ action === 'approve' ? '通过' : '驳回' }}</el-button>
      </template>
    </el-dialog>

    <!-- AI 合同校对 -->
    <el-dialog v-model="aiVisible" title="AI 合同校对（审批单附件 ⇄ 合同管理原件）" width="720px" top="6vh">
      <div v-loading="aiLoading" element-loading-text="AI 校对中，请稍候（约 20-60 秒）…" class="ai-wrap">
        <template v-if="aiResult">
          <div class="ai-meta">
            <el-tag :type="aiResult.engine === 'deepseek' ? 'success' : 'info'" size="small" effect="plain">
              {{ aiResult.engine === 'deepseek' ? 'DeepSeek 比对' : '规则引擎(未接大模型)' }}
            </el-tag>
            <el-tag size="small" :type="aiResult.contract_found ? 'success' : 'danger'" effect="plain">
              {{ aiResult.contract_found ? '合同库已匹配编号' : '合同库无此编号' }}
            </el-tag>
            <el-tag size="small" :type="aiResult.has_form_text ? 'success' : 'warning'" effect="plain">
              审批单附件{{ aiResult.has_form_text ? '已提取' : '无文本' }}
            </el-tag>
            <el-tag size="small" :type="aiResult.has_contract_text ? 'success' : 'warning'" effect="plain">
              合同原件{{ aiResult.has_contract_text ? '已提取' : '无文本' }}
            </el-tag>
          </div>
          <div class="md-body" v-html="aiHtml"></div>
        </template>
        <el-empty v-else-if="!aiLoading" :image-size="60" description="暂无校对结果" />
      </div>
      <template #footer>
        <template v-if="aiCurrent && aiCurrent.attachment_name">
          <el-button :icon="View" @click="previewFormAttachment(aiCurrent)">预览附件</el-button>
          <el-button :icon="Download" @click="downloadFormAttachment(aiCurrent)">下载附件</el-button>
        </template>
        <el-button @click="aiVisible = false">关闭</el-button>
        <el-button v-if="aiResult" :icon="CopyDocument" @click="copyAi">复制全文</el-button>
        <el-button type="primary" :loading="aiLoading" @click="runProofread">重新校对</el-button>
      </template>
    </el-dialog>

    <!-- 详情：字段 + 流转时间轴 -->
    <el-dialog v-model="detailVisible" title="审批单详情" width="680px" top="6vh">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="单据类型">{{ detail.form_type_label }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ detail.status_label }}</el-descriptions-item>
          <el-descriptions-item label="申请部门">{{ detail.department || '—' }}</el-descriptions-item>
          <el-descriptions-item label="申请日期">{{ detail.apply_date || '—' }}</el-descriptions-item>
          <el-descriptions-item label="客户名称">{{ detail.customer_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="业务类型">{{ detail.business_type || '—' }}</el-descriptions-item>
          <el-descriptions-item label="合同编号">{{ detail.contract_no || '—' }}</el-descriptions-item>
          <el-descriptions-item label="业务情况">{{ detail.business_desc || '—' }}</el-descriptions-item>
          <template v-if="detail.form_type === 'payment'">
            <el-descriptions-item label="付款金额">{{ Number(detail.amount).toLocaleString() }}</el-descriptions-item>
            <el-descriptions-item label="金额大写">{{ detail.amount_words || '—' }}</el-descriptions-item>
            <el-descriptions-item label="开户行">{{ detail.bank_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="银行账号">{{ detail.bank_account || '—' }}</el-descriptions-item>
            <el-descriptions-item label="备注" :span="2">{{ detail.remark || '—' }}</el-descriptions-item>
          </template>
          <el-descriptions-item label="合同附件" :span="2">
            <template v-if="detail.attachment_name">
              <span class="att-name">{{ detail.attachment_name }}</span>
              <el-button size="small" link type="primary" :icon="View" @click="previewFormAttachment(detail)">预览</el-button>
              <el-button size="small" link type="primary" :icon="Download" @click="downloadFormAttachment(detail)">下载</el-button>
            </template>
            <span v-else>未上传</span>
          </el-descriptions-item>
        </el-descriptions>

        <div class="timeline-title">审批流转记录</div>
        <el-timeline v-if="actions.length">
          <el-timeline-item
            v-for="a in actions" :key="a.id"
            :type="a.action === 'approve' ? 'success' : 'danger'"
            :timestamp="String(a.created_at).slice(0, 19).replace('T', ' ')"
          >
            <div class="tl-row">
              <b>{{ a.role_label }}</b> · {{ a.approver_name }}
              <el-tag size="small" :type="a.action === 'approve' ? 'success' : 'danger'" effect="plain">
                {{ a.action === 'approve' ? '通过' : '驳回' }}
              </el-tag>
            </div>
            <div v-if="a.comment" class="tl-comment">{{ a.comment }}</div>
            <img v-if="a.signature_snapshot" :src="a.signature_snapshot" class="tl-sig" alt="签名" />
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else :image-size="48" description="尚无流转记录（未提交）" />
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, Plus, ArrowDown, Edit, Delete, Refresh, View, Download, UploadFilled,
  MagicStick, CopyDocument, Money, Document, Printer
} from '@element-plus/icons-vue'
import { marked } from 'marked'
import { useUserStore } from '@/store/user'
import { ROLES, STATUS_META, CONTRACT_TYPE_LABELS } from '@/constants/business'
import { digitToRMB } from '@/utils/rmb'
import { previewBlob, downloadBlob } from '@/utils/file'
import {
  listForms, createForm, updateForm, deleteForm, submitForm,
  uploadFormAttachment, approveForm, rejectForm, listActions,
  proofreadForm, downloadFormPrint, getForm, fetchFormAttachmentBlob
} from '@/api/approval'
import { listCustomers } from '@/api/customer'

const userStore = useUserStore()
const isSuperuser = computed(() => userStore.isSuperuser)
const isBusinessHandler = computed(
  () => userStore.role === ROLES.BUSINESS_HANDLER || userStore.isSuperuser
)

function canApprove(row) {
  if (row.status !== 'pending') return false
  return userStore.isSuperuser || row.current_role === userStore.role
}

const loading = ref(false)
const list = ref([])
const keyword = ref('')
const filteredList = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return list.value
  return list.value.filter((f) =>
    [f.customer_name, f.business_type, f.contract_no]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(kw))
  )
})

async function load() {
  loading.value = true
  try {
    list.value = await listForms()
  } finally {
    loading.value = false
  }
}

// 客户库（客户名称外键联动）
const customers = ref([])
async function loadCustomers() {
  try { customers.value = await listCustomers() } catch { /* 不阻断 */ }
}
function onCustomerChange(id) {
  const c = customers.value.find((x) => x.id === id)
  form.customer_name = c ? c.name : ''
}

// 新建 / 编辑
const dialogVisible = ref(false)
const saving = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const formRef = ref()
const pickedFile = ref(null)
const emptyForm = () => ({
  form_type: 'payment',
  department: '',
  apply_date: null,
  customer_id: null,
  customer_name: '',
  business_type: '',
  business_desc: '详见合同',
  contract_no: '',
  amount: 0,
  bank_name: '',
  bank_account: '',
  remark: '',
  attachment_name: ''
})
const form = reactive(emptyForm())
const rules = {
  customer_id: [{ required: true, message: '请选择客户', trigger: 'change' }],
  contract_no: [{ required: true, message: '请输入合同编号', trigger: 'blur' }],
  amount: [{ required: true, message: '请输入付款金额', trigger: 'blur' }]
}
const dialogTitle = computed(() => {
  const t = CONTRACT_TYPE_LABELS[form.form_type] || '审批单'
  return (isEdit.value ? '编辑' : '新建') + t
})
const amountWordsPreview = computed(() =>
  form.amount > 0 ? '人民币' + digitToRMB(form.amount) : '人民币零元整'
)

function openCreate(type) {
  isEdit.value = false
  editingId.value = null
  pickedFile.value = null
  Object.assign(form, emptyForm(), { form_type: type })
  formRef.value?.clearValidate?.()
  dialogVisible.value = true
}
function openEdit(row) {
  isEdit.value = true
  editingId.value = row.id
  pickedFile.value = null
  Object.assign(form, {
    form_type: row.form_type,
    department: row.department,
    apply_date: row.apply_date || null,
    customer_id: row.customer_id || null,
    customer_name: row.customer_name || '',
    business_type: row.business_type || '',
    business_desc: row.business_desc || '详见合同',
    contract_no: row.contract_no || '',
    amount: Number(row.amount || 0),
    bank_name: row.bank_name || '',
    bank_account: row.bank_account || '',
    remark: row.remark || '',
    attachment_name: row.attachment_name || ''
  })
  formRef.value?.clearValidate?.()
  dialogVisible.value = true
}
async function onSave() {
  await formRef.value?.validate()
  saving.value = true
  try {
    const { attachment_name, ...payload } = form
    let formId = editingId.value
    if (isEdit.value) {
      await updateForm(editingId.value, payload)
    } else {
      const created = await createForm(payload)
      formId = created?.id
    }
    if (pickedFile.value && formId) {
      try {
        await uploadFormAttachment(formId, pickedFile.value)
      } catch {
        ElMessage.warning('审批单已保存，但附件上传失败，请在编辑中重试')
      }
    }
    ElMessage.success(isEdit.value ? '修改成功' : '创建成功')
    dialogVisible.value = false
    load()
  } finally {
    saving.value = false
  }
}
function onFileChange(file) {
  const raw = file?.raw
  if (!raw) return
  if (!raw.name.toLowerCase().endsWith('.pdf')) {
    ElMessage.error('合同附件仅支持 PDF 格式')
    return
  }
  if (raw.size > 20 * 1024 * 1024) {
    ElMessage.error('附件超过 20MB 上限')
    return
  }
  pickedFile.value = raw
}

async function onSubmit(row) {
  await submitForm(row.id)
  ElMessage.success('已提交审批，进入审批流')
  load()
}

// 通过 / 驳回
const actionVisible = ref(false)
const actionSaving = ref(false)
const action = ref('approve')
const actionCurrent = ref(null)
const actionFormRef = ref()
const actionForm = reactive({ comment: '' })
const actionRules = computed(() => ({
  comment: action.value === 'reject'
    ? [{ required: true, message: '请输入驳回原因', trigger: 'blur' }]
    : []
}))
function openAction(row, act) {
  actionCurrent.value = row
  action.value = act
  actionForm.comment = ''
  actionVisible.value = true
  actionFormRef.value?.clearValidate?.()
}
async function confirmAction() {
  await actionFormRef.value?.validate()
  actionSaving.value = true
  try {
    if (action.value === 'approve') {
      await approveForm(actionCurrent.value.id, actionForm.comment)
      ElMessage.success('已通过并附加电子签名')
    } else {
      await rejectForm(actionCurrent.value.id, actionForm.comment)
      ElMessage.success('已驳回')
    }
    actionVisible.value = false
    load()
  } finally {
    actionSaving.value = false
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除该${row.form_type_label}（${row.contract_no || '无编号'}）吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' }
    )
  } catch { return }
  await deleteForm(row.id)
  ElMessage.success('删除成功')
  load()
}

// 打印导出（服务端填充 xlsx 模板）
async function onPrint(row) {
  try {
    const blob = await downloadFormPrint(row.id)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${row.form_type_label}_${row.contract_no || row.id}.xlsx`
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success('已导出审批单')
  } catch {
    ElMessage.error('打印导出失败')
  }
}

// 详情 + 流转记录
const detailVisible = ref(false)
const detail = ref(null)
const actions = ref([])
async function openDetail(row) {
  detail.value = row
  actions.value = []
  detailVisible.value = true
  try {
    const [d, acts] = await Promise.all([getForm(row.id), listActions(row.id)])
    detail.value = d
    actions.value = acts
  } catch { /* 忽略 */ }
}

// 合同附件：预览 / 下载（任意登录用户可用）
async function previewFormAttachment(row) {
  if (!row?.attachment_name) return
  try {
    const blob = await fetchFormAttachmentBlob(row.id)
    previewBlob(blob, row.attachment_name)
  } catch {
    ElMessage.error('附件预览失败')
  }
}
async function downloadFormAttachment(row) {
  if (!row?.attachment_name) return
  try {
    const blob = await fetchFormAttachmentBlob(row.id)
    downloadBlob(blob, row.attachment_name)
  } catch {
    ElMessage.error('附件下载失败')
  }
}

// AI 合同校对
const aiVisible = ref(false)
const aiLoading = ref(false)
const aiResult = ref(null)
const aiCurrent = ref(null)
const aiHtml = computed(() => (aiResult.value ? marked.parse(aiResult.value.markdown || '') : ''))
function openProofread(row) {
  aiCurrent.value = row
  aiResult.value = null
  aiVisible.value = true
  runProofread()
}
async function runProofread() {
  if (!aiCurrent.value) return
  aiLoading.value = true
  try {
    aiResult.value = await proofreadForm(aiCurrent.value.id)
  } catch {
    ElMessage.error('AI 校对失败，请稍后重试')
  } finally {
    aiLoading.value = false
  }
}
function copyAi() {
  navigator.clipboard?.writeText(aiResult.value?.markdown || '').then(
    () => ElMessage.success('校对全文已复制'),
    () => ElMessage.error('复制失败')
  )
}

load()
loadCustomers()
</script>

<style scoped lang="scss">
.card-header { display: flex; justify-content: space-between; align-items: center; }
.approval-form :deep(.el-form-item__label) { white-space: nowrap; }
.toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; gap: 12px; }
.search-input { max-width: 340px; }
.toolbar-right { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
/* 新建审批下拉按钮：Hover 平滑过渡，箭头微动，贴合系统 Element Plus 风格 */
.new-approval-dropdown :deep(.el-button) { transition: all 0.25s ease; }
.new-approval-dropdown .el-icon--right { transition: transform 0.25s ease; }
.new-approval-dropdown:hover .el-icon--right { transform: translateY(2px); }
.cur-role { margin-top: 4px; font-size: 12px; color: #e6a23c; }
.op-cell { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; }
.op-cell :deep(.el-button) { margin: 0; }
.muted { color: var(--el-text-color-secondary); }
.mb { margin-bottom: 12px; }
.upload-mock {
  width: 100%;
  :deep(.el-upload), :deep(.el-upload-dragger) { width: 100%; }
  :deep(.el-upload-dragger) { padding: 16px; }
}
.upload-tip { color: var(--el-text-color-secondary); font-size: 12px; margin-top: 4px; }
.upload-tip .picked { color: #67c23a; margin-left: 8px; }
.ai-wrap { min-height: 120px; }
.ai-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.md-body { line-height: 1.75; color: var(--el-text-color-primary); max-height: 62vh; overflow: auto; }
.md-body :deep(h2) { font-size: 16px; margin: 16px 0 8px; color: var(--el-color-primary); }
.md-body :deep(strong) { color: var(--el-color-danger); }
.md-body :deep(table) { border-collapse: collapse; width: 100%; }
.md-body :deep(th), .md-body :deep(td) { border: 1px solid var(--el-border-color); padding: 6px 8px; }
.timeline-title { font-weight: 600; margin: 18px 0 10px; color: var(--el-color-primary); }
.tl-row { display: flex; align-items: center; gap: 8px; }
.tl-comment { color: var(--el-text-color-regular); font-size: 13px; margin-top: 2px; }
.tl-sig { max-height: 44px; margin-top: 4px; }
</style>
