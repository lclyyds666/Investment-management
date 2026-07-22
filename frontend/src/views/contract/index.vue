<template>
  <div class="contract" v-loading="loading">
    <el-card shadow="never">
      <template #header>
        <div class="card-header"><span>合同管理</span></div>
      </template>

      <!-- 工具栏：新建 + 搜索 + 刷新 -->
      <div class="toolbar">
        <el-input v-model="keyword" placeholder="搜索合同编号 / 名称 / 客户" clearable class="search-input">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <div class="toolbar-right">
          <el-button v-if="isBusinessHandler" type="primary" :icon="Plus" @click="openCreate">
            新建合同
          </el-button>
          <el-button :icon="Tickets" @click="openLedger">生成合同台账</el-button>
          <el-button v-if="isSuperuser" :icon="Collection" @click="openKb">法规知识库</el-button>
          <el-button :icon="Refresh" @click="load">刷新</el-button>
        </div>
      </div>

      <el-table :data="filteredList" border stripe>
        <el-table-column prop="contract_no" label="合同编号" width="150" />
        <el-table-column prop="title" label="合同名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="customer_name" label="客户名称" min-width="130" show-overflow-tooltip />
        <el-table-column label="金额(元)" width="130" align="right">
          <template #default="{ row }">{{ Number(row.amount).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column label="状态 / 当前环节" width="160" align="center">
          <template #default="{ row }">
            <el-tag :type="STATUS_META[row.status]?.type">{{ row.status_label }}</el-tag>
            <div v-if="row.current_role_label" class="cur-role">→ {{ row.current_role_label }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="340" align="center">
          <template #default="{ row }">
            <div class="op-cell">
              <el-button size="small" type="info" :icon="View" @click="openDetail(row)">详情</el-button>
              <el-button size="small" color="#626aef" :icon="MagicStick" @click="openAiReview(row)">AI 审查</el-button>
              <template v-if="row.attachment_name">
                <el-button size="small" type="primary" plain :icon="View" @click="previewContractAttachment(row)">预览附件</el-button>
                <el-button size="small" type="primary" plain :icon="Download" @click="downloadContractAttachment(row)">下载附件</el-button>
              </template>
              <template v-if="isBusinessHandler && ['draft', 'rejected'].includes(row.status)">
                <el-button size="small" type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
                <el-button size="small" type="success" @click="onSubmit(row)">提交审批</el-button>
                <el-button size="small" type="danger" :icon="Delete" @click="onDelete(row)">删除</el-button>
              </template>
              <template v-if="canApprove(row)">
                <el-button size="small" type="success" @click="openAction(row, 'approve')">通过</el-button>
                <el-button size="small" type="warning" @click="openAction(row, 'reject')">驳回</el-button>
              </template>
              <!-- 精细化管控：已通过合同仅超级管理员可删除（非超管此按钮不渲染） -->
              <el-button
                v-if="canDeleteApproved(row)"
                size="small" type="danger" :icon="Delete" @click="onDelete(row)"
              >
                删除
              </el-button>
            </div>
          </template>
        </el-table-column>
        <template #empty>暂无合同数据</template>
      </el-table>
    </el-card>

    <!-- 新建 / 编辑合同 -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑合同' : '新建合同'" width="640px" top="6vh">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px" class="contract-form">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="申请部门"><el-input v-model="form.department" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="合同编号" prop="contract_no">
              <el-input v-model="form.contract_no" :disabled="isEdit" placeholder="如 HT-2026-010" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="合同名称" prop="title">
          <el-input v-model="form.title" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="合同类型" prop="contract_type">
              <el-input v-model="form.contract_type" placeholder="请输入合同类型" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="是否内部合同">
              <el-switch v-model="form.is_internal" active-text="是" inactive-text="否" inline-prompt />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="合同标的">
          <el-input v-model="form.subject" placeholder="合同标的物 / 服务内容" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="客户名称">
              <el-select
                v-model="form.customer_name"
                filterable allow-create default-first-option clearable
                placeholder="选择或输入客户名称"
                style="width: 100%"
                @change="onCustomerChange"
              >
                <el-option v-for="c in customers" :key="c.id" :label="c.name" :value="c.name" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="签订日期">
              <el-date-picker v-model="form.sign_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="客户社会信用代码">
          <el-input v-model="form.customer_credit_code" placeholder="选择客户名称后自动填充，可手动修改" />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="合同金额" prop="amount">
              <el-input-number v-model="form.amount" :min="0" :step="10000" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="币种">
              <el-select v-model="form.currency" style="width: 100%">
                <el-option v-for="c in CURRENCIES" :key="c" :label="c" :value="c" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="付款条件">
          <el-input v-model="form.payment_terms" type="textarea" :rows="2" placeholder="如：验收后 30 日内付款 / 分期付款安排等" />
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="合同附件">
          <el-upload
            class="upload-mock"
            drag
            action="#"
            :auto-upload="false"
            :show-file-list="false"
            :limit="1"
            accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg"
            :on-change="onFileChange"
            :on-exceed="() => ElMessage.warning('仅可上传一个附件')"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">点击或拖拽文件到此处<em>上传合同附件</em></div>
            <template #tip>
              <div class="upload-tip">
                支持 PDF / Word / Excel / 图片，单个 ≤ 20MB
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

    <!-- 合同台账 -->
    <el-dialog v-model="ledgerVisible" title="合同台账" width="92%" top="5vh">
      <div class="ledger-toolbar">
        <span class="ledger-count">共 {{ list.length }} 条合同</span>
        <el-button type="primary" size="small" :icon="Download" @click="exportLedger">导出 CSV</el-button>
      </div>
      <el-table :data="list" border stripe size="small" max-height="60vh">
        <el-table-column type="index" label="#" width="50" align="center" />
        <el-table-column prop="contract_no" label="合同编号" width="130" />
        <el-table-column prop="title" label="合同名称" min-width="160" show-overflow-tooltip />
        <el-table-column label="合同类型" width="120" align="center">
          <template #default="{ row }">{{ row.contract_type_label }}</template>
        </el-table-column>
        <el-table-column label="是否内部合同" width="110" align="center">
          <template #default="{ row }">{{ row.is_internal ? '是' : '否' }}</template>
        </el-table-column>
        <el-table-column prop="subject" label="合同标的" min-width="140" show-overflow-tooltip />
        <el-table-column prop="sign_date" label="签订日期" width="110" align="center" />
        <el-table-column prop="customer_credit_code" label="客户社会信用代码" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">{{ row.customer_credit_code || '—' }}</template>
        </el-table-column>
        <el-table-column prop="customer_name" label="客户名称" min-width="130" show-overflow-tooltip />
        <el-table-column label="合同金额" width="130" align="right">
          <template #default="{ row }">{{ Number(row.amount).toLocaleString() }}</template>
        </el-table-column>
        <el-table-column prop="currency" label="币种" width="80" align="center" />
        <el-table-column prop="payment_terms" label="付款条件" min-width="140" show-overflow-tooltip />
        <template #empty>暂无合同数据</template>
      </el-table>
    </el-dialog>

    <!-- 合同审批：通过 / 驳回（法律合同审批，供当前环节审批人操作） -->
    <el-dialog
      v-model="actionVisible"
      :title="action === 'approve' ? '审批通过 - 审批意见' : '驳回 - 请输入驳回原因'"
      width="480px"
    >
      <el-alert
        v-if="action === 'approve'"
        type="success" :closable="false" show-icon
        title="通过后将自动附加您的电子签名，并流转至下一审批环节"
        class="mb"
      />
      <el-form ref="actionFormRef" :model="actionForm" :rules="actionRules">
        <el-form-item prop="comment">
          <el-input
            v-model="actionForm.comment"
            type="textarea" :rows="4"
            :placeholder="action === 'approve' ? '请输入审批意见（可选）' : '请输入驳回原因（必填）'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="actionVisible = false">取消</el-button>
        <el-button
          :type="action === 'approve' ? 'success' : 'danger'"
          :loading="actionSaving" @click="confirmAction"
        >
          确认{{ action === 'approve' ? '通过' : '驳回' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- AI 合同审查结果 -->
    <el-dialog v-model="aiVisible" title="AI 合同审查" width="720px" top="6vh">
      <div v-loading="aiLoading" element-loading-text="AI 审查中，请稍候（约 20-60 秒）…" class="ai-wrap">
        <template v-if="aiResult">
          <div class="ai-meta">
            <el-tag :type="aiResult.engine === 'deepseek' ? 'success' : 'info'" size="small" effect="plain">
              {{ aiResult.engine === 'deepseek' ? 'DeepSeek 综合' : '规则引擎(未接大模型)' }}
            </el-tag>
            <el-tag size="small" :type="aiResult.has_attachment ? 'success' : 'warning'" effect="plain">
              {{ aiResult.has_attachment ? '基于合同附件全文' : '基于合同字段(未上传附件)' }}
            </el-tag>
            <el-tag v-if="aiResult.kb_used && aiResult.kb_used.length" size="small" type="primary" effect="plain">
              参照法规库 {{ aiResult.kb_used.length }} 篇
            </el-tag>
          </div>
          <div class="md-body" v-html="aiHtml"></div>
        </template>
        <el-empty v-else-if="!aiLoading" :image-size="60" description="暂无审查结果" />
      </div>
      <template #footer>
        <template v-if="aiCurrent && aiCurrent.attachment_name">
          <el-button :icon="View" @click="previewContractAttachment(aiCurrent)">预览附件</el-button>
          <el-button :icon="Download" @click="downloadContractAttachment(aiCurrent)">下载附件</el-button>
        </template>
        <el-button @click="aiVisible = false">关闭</el-button>
        <el-button v-if="aiResult" :icon="CopyDocument" @click="copyAi">复制全文</el-button>
        <el-button type="primary" :loading="aiLoading" @click="runAiReview">重新审查</el-button>
      </template>
    </el-dialog>

    <!-- 法规知识库(超管维护) -->
    <el-dialog v-model="kbVisible" title="法规知识库" width="720px" top="6vh">
      <el-alert
        type="info" :closable="false" show-icon class="mb"
        title="上传公司合同法 / 集团企业制度 / 法律规范等文件（PDF/Word/Excel），AI 审查合同时会自动引用作为分析依据。"
      />
      <div class="kb-toolbar">
        <el-select v-model="kbCategory" size="small" style="width: 160px">
          <el-option v-for="k in KB_CATEGORIES" :key="k" :label="k" :value="k" />
        </el-select>
        <el-upload
          :auto-upload="false" :show-file-list="false" accept=".pdf,.docx,.xlsx" :on-change="onKbUpload"
        >
          <el-button size="small" type="primary" :icon="UploadFilled" :loading="kbUploading">上传法规文件</el-button>
        </el-upload>
        <span class="muted small">支持 PDF / Word / Excel；仅超级管理员可上传/删除</span>
      </div>
      <el-table :data="kbList" border size="small" max-height="50vh">
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="120" align="center" />
        <el-table-column prop="file_type" label="类型" width="70" align="center" />
        <el-table-column prop="char_count" label="字数" width="80" align="right" />
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="danger" @click="onKbDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>知识库暂无文件</template>
      </el-table>
    </el-dialog>

    <!-- 合同详情（流转时间轴 + 打印审批单） -->
    <ContractDetailDrawer v-model="detailVisible" :contract-id="detailId" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus, Edit, Delete, Refresh, View, UploadFilled, Tickets, Download, MagicStick, Collection, CopyDocument } from '@element-plus/icons-vue'
import { marked } from 'marked'
import { useUserStore } from '@/store/user'
import { useApprovalBadgeStore } from '@/store/approvalBadge'
import { ROLES, STATUS_META } from '@/constants/business'
import { previewBlob, downloadBlob } from '@/utils/file'
import ContractDetailDrawer from '@/components/ContractDetailDrawer.vue'
import {
  listContracts, createContract, updateContract, deleteContract, submitContract,
  uploadContractAttachment, approveContract, rejectContract, aiReviewContract,
  fetchContractAttachmentBlob
} from '@/api/contract'
import { listCustomers } from '@/api/customer'
import { listKnowledge, uploadKnowledge, deleteKnowledge } from '@/api/knowledge'

const CURRENCIES = ['人民币', '美元', '欧元', '港币', '日元']

const userStore = useUserStore()
const badgeStore = useApprovalBadgeStore()
const isSuperuser = computed(() => userStore.isSuperuser)
const isBusinessHandler = computed(
  () => userStore.role === ROLES.BUSINESS_HANDLER || userStore.isSuperuser
)

// 合同(法律)审批：仅当合同处于审批中、且当前环节角色恰为本人(或超管)时，可通过/驳回
function canApprove(row) {
  if (row.status !== 'pending') return false
  return userStore.isSuperuser || row.current_role === userStore.role
}

// 精细化管控：已通过(已审核)合同仅超级管理员可删除；其余用户不显示删除按钮
function canDeleteApproved(row) {
  return row.status === 'approved' && userStore.isSuperuser
}

const loading = ref(false)
const list = ref([])
const keyword = ref('')
const filteredList = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return list.value
  return list.value.filter((c) =>
    [c.contract_no, c.title, c.customer_name, c.party_b]
      .filter(Boolean)
      .some((v) => String(v).toLowerCase().includes(kw))
  )
})

async function load() {
  loading.value = true
  try {
    list.value = await listContracts()
  } finally {
    loading.value = false
  }
}

// 客户列表（用于「客户名称」下拉 + 联动填充社会信用代码）
const customers = ref([])
async function loadCustomers() {
  try { customers.value = await listCustomers() } catch { /* 客户加载失败不阻断合同页 */ }
}
function onCustomerChange(name) {
  const c = customers.value.find((x) => x.name === name)
  if (c) form.customer_credit_code = c.social_credit_code || ''
}

// 新建 / 编辑
const dialogVisible = ref(false)
const saving = ref(false)
const isEdit = ref(false)
const editingId = ref(null)
const formRef = ref()
const pickedFile = ref(null)  // 本次待上传的合同附件（保存后随合同上传）
const emptyForm = () => ({
  contract_no: '',
  title: '',
  contract_type: '',
  department: '',
  is_internal: false,
  subject: '',
  customer_name: '',
  customer_credit_code: '',
  party_a: '山东出版供应链管理公司',
  party_b: '',
  amount: 0,
  currency: '人民币',
  payment_terms: '',
  sign_date: null,
  remark: '',
  attachment_name: ''
})
const form = reactive(emptyForm())
const rules = {
  contract_no: [{ required: true, message: '请输入合同编号', trigger: 'blur' }],
  title: [{ required: true, message: '请输入合同名称', trigger: 'blur' }]
}

function openCreate() {
  isEdit.value = false
  editingId.value = null
  pickedFile.value = null
  Object.assign(form, emptyForm())
  formRef.value?.clearValidate?.()
  dialogVisible.value = true
}
function openEdit(row) {
  isEdit.value = true
  editingId.value = row.id
  pickedFile.value = null
  Object.assign(form, {
    contract_no: row.contract_no,
    title: row.title,
    contract_type: row.contract_type,
    department: row.department,
    is_internal: !!row.is_internal,
    subject: row.subject || '',
    customer_name: row.customer_name,
    customer_credit_code: row.customer_credit_code || '',
    party_a: row.party_a,
    party_b: row.party_b,
    amount: Number(row.amount),
    currency: row.currency || '人民币',
    payment_terms: row.payment_terms || '',
    sign_date: row.sign_date || null,
    remark: row.remark,
    attachment_name: row.attachment_name || ''
  })
  formRef.value?.clearValidate?.()
  dialogVisible.value = true
}
async function onSave() {
  await formRef.value?.validate()
  saving.value = true
  try {
    let contractId = editingId.value
    if (isEdit.value) {
      const { contract_no, attachment_name, ...rest } = form
      await updateContract(editingId.value, { ...rest })
    } else {
      const { attachment_name, ...rest } = form
      const created = await createContract({ ...rest })
      contractId = created?.id
    }
    // 附件：保存合同后再真实上传（覆盖式）
    if (pickedFile.value && contractId) {
      try {
        await uploadContractAttachment(contractId, pickedFile.value)
      } catch (e) {
        ElMessage.warning('合同已保存，但附件上传失败，请在编辑中重试')
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
  if (raw.size > 20 * 1024 * 1024) {
    ElMessage.error('附件超过 20MB 上限')
    return
  }
  pickedFile.value = raw
}

async function onSubmit(row) {
  await submitContract(row.id)
  ElMessage.success('已提交审批，合同进入审批流')
  load()
  badgeStore.refresh() // 提交后可能轮到下一环节角色，实时刷新角标
}

// 合同审批：通过 / 驳回
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
      await approveContract(actionCurrent.value.id, actionForm.comment)
      ElMessage.success('已通过并附加电子签名')
    } else {
      await rejectContract(actionCurrent.value.id, actionForm.comment)
      ElMessage.success('已驳回')
    }
    badgeStore.refresh() // 审批完成后本人待办数减少，实时刷新角标
    actionVisible.value = false
    load()
  } finally {
    actionSaving.value = false
  }
}

// 合同台账
const ledgerVisible = ref(false)
function openLedger() {
  ledgerVisible.value = true
}
function exportLedger() {
  const headers = ['合同编号', '合同名称', '合同类型', '是否内部合同', '合同标的', '签订日期', '客户社会信用代码', '客户名称', '合同金额', '币种', '付款条件']
  const rows = list.value.map((c) => [
    c.contract_no,
    c.title,
    c.contract_type || c.contract_type_label || '',
    c.is_internal ? '是' : '否',
    c.subject || '',
    c.sign_date || '',
    c.customer_credit_code || '',
    c.customer_name || '',
    Number(c.amount || 0),
    c.currency || '',
    (c.payment_terms || '').replace(/\r?\n/g, ' ')
  ])
  const esc = (v) => {
    const s = String(v ?? '')
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  const csv = [headers, ...rows].map((r) => r.map(esc).join(',')).join('\r\n')
  // 加 BOM 确保 Excel 正确识别 UTF-8 中文
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `合同台账_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(a.href)
  ElMessage.success(`已导出 ${rows.length} 条合同台账`)
}
async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除合同「${row.title}」(${row.contract_no})吗？此操作不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确定删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await deleteContract(row.id)
  ElMessage.success('删除成功')
  load()
}

// 合同附件：预览 / 下载（任意有查看权限的登录用户均可）
async function previewContractAttachment(row) {
  if (!row?.attachment_name) return
  try {
    const blob = await fetchContractAttachmentBlob(row.id)
    previewBlob(blob, row.attachment_name)
  } catch {
    ElMessage.error('附件预览失败')
  }
}
async function downloadContractAttachment(row) {
  if (!row?.attachment_name) return
  try {
    const blob = await fetchContractAttachmentBlob(row.id)
    downloadBlob(blob, row.attachment_name)
  } catch {
    ElMessage.error('附件下载失败')
  }
}

// 详情抽屉
const detailVisible = ref(false)
const detailId = ref(null)
function openDetail(row) {
  detailId.value = row.id
  detailVisible.value = true
}

// AI 合同审查
const aiVisible = ref(false)
const aiLoading = ref(false)
const aiResult = ref(null)
const aiCurrent = ref(null)
const aiHtml = computed(() => (aiResult.value ? marked.parse(aiResult.value.markdown || '') : ''))
function openAiReview(row) {
  aiCurrent.value = row
  aiResult.value = null
  aiVisible.value = true
  runAiReview()
}
async function runAiReview() {
  if (!aiCurrent.value) return
  aiLoading.value = true
  try {
    aiResult.value = await aiReviewContract(aiCurrent.value.id)
  } catch (e) {
    ElMessage.error('AI 审查失败，请稍后重试')
  } finally {
    aiLoading.value = false
  }
}
function copyAi() {
  navigator.clipboard?.writeText(aiResult.value?.markdown || '').then(
    () => ElMessage.success('审查全文已复制'),
    () => ElMessage.error('复制失败')
  )
}

// 法规知识库
const KB_CATEGORIES = ['公司合同法', '集团企业制度', '法律规范', '其他']
const kbVisible = ref(false)
const kbList = ref([])
const kbUploading = ref(false)
const kbCategory = ref('法律规范')
async function openKb() {
  kbVisible.value = true
  await loadKb()
}
async function loadKb() {
  try { kbList.value = await listKnowledge() } catch { /* 忽略 */ }
}
async function onKbUpload(file) {
  const raw = file?.raw
  const name = (raw?.name || '').toLowerCase()
  if (!['.pdf', '.docx', '.xlsx'].some((e) => name.endsWith(e))) {
    ElMessage.error('仅支持 PDF / Word(.docx) / Excel(.xlsx)')
    return
  }
  kbUploading.value = true
  try {
    await uploadKnowledge(raw, raw.name.replace(/\.[^.]+$/, ''), kbCategory.value)
    ElMessage.success('已加入法规知识库')
    await loadKb()
  } finally {
    kbUploading.value = false
  }
}
async function onKbDelete(row) {
  try {
    await ElMessageBox.confirm(`确定从知识库删除「${row.title}」吗？`, '删除确认', { type: 'warning' })
  } catch { return }
  await deleteKnowledge(row.id)
  ElMessage.success('已删除')
  await loadKb()
}

onMounted(() => { load(); loadCustomers() })
</script>

<style scoped lang="scss">
.card-header { display: flex; justify-content: space-between; align-items: center; }
/* 表单标签统一不换行，避免「客户社会信用代码」等长标签跨行错位 */
.contract-form :deep(.el-form-item__label) { white-space: nowrap; }
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 12px;
}
.search-input { max-width: 340px; }
.toolbar-right { display: flex; gap: 8px; }
.cur-role { margin-top: 4px; font-size: 12px; color: #e6a23c; }
/* 操作栏:填充按钮(白色字体)+ 自动换行,避免拥挤/看不清 */
.op-cell { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; }
.op-cell :deep(.el-button) { margin: 0; }
.mb { margin-bottom: 12px; }
.upload-mock {
  width: 100%;
  :deep(.el-upload),
  :deep(.el-upload-dragger) { width: 100%; }
  :deep(.el-upload-dragger) { padding: 16px; }
}
.upload-tip { color: var(--el-text-color-secondary); font-size: 12px; margin-top: 4px; }
.upload-tip .picked { color: #67c23a; margin-left: 8px; }
.ledger-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.ledger-count { color: var(--el-text-color-secondary); font-size: 13px; }
.muted { color: var(--el-text-color-secondary); }
.small { font-size: 12px; }
/* AI 审查 */
.ai-wrap { min-height: 120px; }
.ai-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.md-body { line-height: 1.75; color: var(--el-text-color-primary); max-height: 62vh; overflow: auto; }
.md-body :deep(h2) { font-size: 16px; margin: 16px 0 8px; color: var(--el-color-primary); }
.md-body :deep(h3) { font-size: 14px; margin: 12px 0 6px; }
.md-body :deep(ul), .md-body :deep(ol) { padding-left: 22px; }
.md-body :deep(p) { margin: 6px 0; }
.md-body :deep(strong) { color: var(--el-color-danger); }
.md-body :deep(table) { border-collapse: collapse; width: 100%; }
.md-body :deep(th), .md-body :deep(td) { border: 1px solid var(--el-border-color); padding: 6px 8px; }
/* 知识库 */
.kb-toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
</style>
