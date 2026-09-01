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
          <el-button
            v-if="canCreate"
            data-testid="create-contract"
            type="primary"
            :icon="Plus"
            :disabled="!canOpenCreate"
            @click="openCreate"
          >
            新建合同
          </el-button>
          <el-button :icon="Tickets" @click="openLedger">生成合同台账</el-button>
          <el-button v-if="canViewKnowledge" :icon="Collection" @click="openKb">法规知识库</el-button>
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
              <el-button size="small" class="btn-ai" :icon="MagicStick" @click="openAiReview(row)">AI 审查</el-button>
              <template v-if="row.attachment_name && canExport">
                <el-button size="small" type="primary" plain :icon="View" @click="previewContractAttachment(row)">预览附件</el-button>
                <el-button size="small" type="primary" plain :icon="Download" @click="downloadContractAttachment(row)">下载附件</el-button>
              </template>
              <el-button v-if="canUpdate && ['draft', 'rejected'].includes(row.status)" size="small" type="primary" :icon="Edit" @click="openEdit(row)">编辑</el-button>
              <el-button v-if="canSubmit && ['draft', 'rejected'].includes(row.status)" size="small" type="success" @click="onSubmit(row)">提交审批</el-button>
              <el-button v-if="canDelete && ['draft', 'rejected'].includes(row.status)" size="small" type="danger" :icon="Delete" @click="onDelete(row)">删除</el-button>
              <el-button v-if="canApprove(row)" size="small" type="success" @click="openAction(row, 'approve')">通过</el-button>
              <el-button v-if="canReturn(row)" size="small" type="warning" @click="openAction(row, 'reject')">退回</el-button>
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
            <el-form-item v-if="!isEdit" label="发起归属" :prop="isSuperuser ? 'organization_code' : 'initiator_assignment_id'">
              <el-select
                v-if="isSuperuser"
                v-model="form.organization_code"
                placeholder="请选择发起归属"
                style="width: 100%"
                @change="onInitiatorOrganizationChange"
              >
                <el-option
                  v-for="option in initiatorOptions"
                  :key="option.organization_code"
                  :label="option.organization_name"
                  :value="option.organization_code"
                />
              </el-select>
              <el-input
                v-else-if="initiatorOptions.length === 1"
                :model-value="initiatorOptions[0].organization_name"
                readonly
              />
              <el-select
                v-else
                v-model="form.initiator_assignment_id"
                placeholder="请选择发起归属"
                style="width: 100%"
                @change="onInitiatorAssignmentChange"
              >
                <el-option
                  v-for="option in initiatorOptions"
                  :key="option.assignment_id"
                  :label="option.organization_name"
                  :value="option.assignment_id"
                />
              </el-select>
            </el-form-item>
          </el-col>
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

    <el-dialog
      v-model="submitVisible"
      title="提交合同审批"
      width="680px"
      top="6vh"
      :close-on-click-modal="!submitSaving"
      @closed="resetSubmitDialog"
    >
      <DesignatedApproverFields
        v-if="submitVisible"
        ref="submitFieldsRef"
        v-model="selectedApprovers"
        :workflow-code="submitPlan?.workflow_code || ''"
        :nodes="submitNodes"
        target-type="contract"
        :target-id="submitCurrent?.id || null"
        :exclude-user-id="userStore.userInfo?.id"
      />
      <template #footer>
        <el-button :disabled="submitSaving" @click="submitVisible = false">取消</el-button>
        <el-button data-testid="confirm-submit" type="primary" :loading="submitSaving" @click="confirmSubmit">
          确认提交
        </el-button>
      </template>
    </el-dialog>

    <!-- 合同台账 -->
    <el-dialog v-model="ledgerVisible" title="合同台账" width="92%" top="5vh">
      <div class="ledger-toolbar">
        <span class="ledger-count">共 {{ list.length }} 条合同</span>
        <el-button v-if="canExport" data-testid="export-contract-ledger" type="primary" size="small" :icon="Download" @click="exportLedger">导出 CSV</el-button>
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

    <!-- 合同审批：通过 / 退回（仅当前 active_task 可办理人操作） -->
    <el-dialog
      v-model="actionVisible"
      :title="action === 'approve' ? '审批通过 - 审批意见' : '退回 - 请输入退回原因'"
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
            :placeholder="action === 'approve' ? '请输入审批意见（可选）' : '请输入退回原因（必填）'"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="actionVisible = false">取消</el-button>
        <el-button
          :type="action === 'approve' ? 'success' : 'danger'"
          :loading="actionSaving" @click="confirmAction"
        >
          确认{{ action === 'approve' ? '通过' : '退回' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- AI 合同审查结果 -->
    <el-dialog v-model="aiVisible" title="AI 合同审查" width="720px" top="6vh">
      <div v-loading="aiLoading" element-loading-text="AI 审查中，请稍候（约 20-60 秒）…" class="ai-wrap">
        <template v-if="aiResult">
          <div class="ai-meta">
            <span class="ai-meta-tag" :class="aiResult.engine === 'deepseek' ? 'is-success' : 'is-info'">
              {{ aiResult.engine === 'deepseek' ? 'DeepSeek 综合' : '规则引擎(未接大模型)' }}
            </span>
            <span class="ai-meta-tag" :class="aiResult.has_attachment ? 'is-success' : 'is-warning'">
              {{ aiResult.has_attachment ? '基于合同附件全文' : '基于合同字段(未上传附件)' }}
            </span>
            <span v-if="aiResult.kb_used && aiResult.kb_used.length" class="ai-meta-tag is-primary">
              参照法规库 {{ aiResult.kb_used.length }} 篇
            </span>
            <span v-if="aiResult.retrieved_sources && aiResult.retrieved_sources.length" class="ai-meta-tag is-primary">
              检索证据 {{ aiResult.retrieved_sources.length }} 篇
            </span>
            <span v-if="aiResult.coverage" class="ai-meta-tag is-warning">
              证据覆盖率 {{ coverageRate }}
            </span>
          </div>
          <div
            v-if="aiResult.fallback_reason"
            class="ai-fallback"
            role="alert"
          >{{ fallbackLabel }}</div>
          <section v-if="allAiFindings.length" class="ai-findings" aria-label="事实核验结果">
            <div class="ai-section-title">事实核验与风险发现</div>
            <div v-for="(item, index) in allAiFindings" :key="`${item.claim || item.title || 'finding'}-${index}`" class="ai-finding">
              <div class="ai-finding-head">
                <span class="ai-claim">{{ item.claim || item.title || '未命名主张' }}</span>
                <span class="ai-verdict" :class="`is-${verdictMeta(item.verdict).type}`">
                  {{ verdictMeta(item.verdict).label }}
                </span>
                <span v-if="item.risk_level" class="ai-verdict ai-risk" :class="`is-${riskMeta(item.risk_level).type}`">
                  {{ riskMeta(item.risk_level).label }}风险
                </span>
              </div>
              <div v-if="item.contract_quote" class="ai-quote">合同原文：{{ item.contract_quote }}</div>
              <div v-if="item.reason" class="ai-finding-line">核验说明：{{ item.reason }}</div>
              <div v-if="item.suggestion" class="ai-finding-line">修改建议：{{ item.suggestion }}</div>
              <details v-if="item.evidence && item.evidence.length" class="ai-evidence">
                <summary>查看证据原文（{{ item.evidence.length }}）</summary>
                <div v-for="source in item.evidence" :key="source.chunk_id || `${source.title}-${source.section}`" class="ai-evidence-item">
                  <div class="ai-evidence-title">{{ source.title || '法规知识库' }}<span v-if="source.section"> · {{ source.section }}</span></div>
                  <div class="ai-evidence-text">{{ source.text }}</div>
                </div>
              </details>
              <div v-else-if="item.verdict === 'not_found'" class="ai-not-found">知识库未找到支持该主张的依据</div>
            </div>
          </section>
          <details v-if="aiResult.retrieved_sources && aiResult.retrieved_sources.length" class="ai-evidence ai-all-evidence">
            <summary>查看本次召回的法规原文（{{ aiResult.retrieved_sources.length }} 篇）</summary>
            <div v-for="source in aiResult.retrieved_sources" :key="source.chunk_id || `${source.title}-${source.section}`" class="ai-evidence-item">
              <div class="ai-evidence-title">{{ source.title || '法规知识库' }}<span v-if="source.section"> · {{ source.section }}</span></div>
              <div class="ai-evidence-text">{{ source.text }}</div>
            </div>
          </details>
          <div class="md-body" v-html="aiHtml"></div>
        </template>
        <el-empty v-else-if="!aiLoading" :image-size="60" description="暂无审查结果" />
      </div>
      <template #footer>
        <template v-if="aiCurrent && aiCurrent.attachment_name && canExport">
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
      <div v-if="canManageKnowledge" class="kb-toolbar">
        <el-select v-model="kbCategory" size="small" style="width: 160px">
          <el-option v-for="k in KB_CATEGORIES" :key="k" :label="k" :value="k" />
        </el-select>
        <el-upload
          :auto-upload="false" :show-file-list="false" accept=".pdf,.docx,.xlsx" :on-change="onKbUpload"
        >
          <el-button size="small" type="primary" :icon="UploadFilled" :loading="kbUploading">上传法规文件</el-button>
        </el-upload>
        <span class="muted small">支持 PDF / Word / Excel</span>
      </div>
      <el-table :data="kbList" border size="small" max-height="50vh">
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="120" align="center" />
        <el-table-column prop="file_type" label="类型" width="70" align="center" />
        <el-table-column prop="char_count" label="字数" width="80" align="right" />
        <el-table-column v-if="canManageKnowledge" label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="danger" @click="onKbDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>知识库暂无文件</template>
      </el-table>
    </el-dialog>

    <!-- 合同详情（流转时间轴 + 打印审批单） -->
    <ContractDetailDrawer ref="detailDrawerRef" v-model="detailVisible" :contract-id="detailId" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus, Edit, Delete, Refresh, View, UploadFilled, Tickets, Download, MagicStick, Collection, CopyDocument } from '@element-plus/icons-vue'
import { usePortalStore } from '@/store/portal'
import { useUserStore } from '@/store/user'
import { useApprovalBadgeStore } from '@/store/approvalBadge'
import { COMPANY_NAMES, STATUS_META } from '@/constants/business'
import { canUsePermission } from '@/utils/businessAuthorization'
import { renderSafeMarkdown } from '@/utils/safeMarkdown'
import { previewBlob, downloadBlob } from '@/utils/file'
import ContractDetailDrawer from '@/components/ContractDetailDrawer.vue'
import DesignatedApproverFields from '@/components/workflow/DesignatedApproverFields.vue'
import {
  listContracts, createContract, updateContract, deleteContract, submitContract,
  uploadContractAttachment, approveContract, rejectContract, aiReviewContract,
  exportContracts, fetchContractAttachmentBlob
} from '@/api/contract'
import { listCustomers } from '@/api/customer'
import { listKnowledge, uploadKnowledge, deleteKnowledge } from '@/api/knowledge'
import { listLegalInitiatorOptions } from '@/api/legalRisk'
import { getWorkflowSubmissionPlan } from '@/api/workflow'

const CURRENCIES = ['人民币', '美元', '欧元', '港币', '日元']

const portalStore = usePortalStore()
const userStore = useUserStore()
const badgeStore = useApprovalBadgeStore()
const isSuperuser = computed(() => portalStore.isSuperuser)
const canCreate = computed(() => canUsePermission(portalStore, 'investment.legal.contracts.create'))
const canUpdate = computed(() => canUsePermission(portalStore, 'investment.legal.contracts.update'))
const canDelete = computed(() => canUsePermission(portalStore, 'investment.legal.contracts.delete'))
const canSubmit = computed(() => canUsePermission(portalStore, 'investment.legal.contracts.submit'))
const canExport = computed(() => canUsePermission(portalStore, 'investment.legal.contracts.export'))
const canViewKnowledge = computed(() => canUsePermission(portalStore, 'investment.legal.contracts.view'))
const canManageKnowledge = computed(() => canUsePermission(portalStore, 'investment.legal.contracts.update'))

function canApprove(row) {
  return Boolean(row.active_task && row.can_act)
}

function canReturn(row) {
  return Boolean(row.active_task && row.can_act)
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

const initiatorOptions = ref([])
const initiatorOptionsLoading = ref(true)
const canOpenCreate = computed(() => canCreate.value && !initiatorOptionsLoading.value && initiatorOptions.value.length > 0)
async function loadInitiatorOptions() {
  initiatorOptionsLoading.value = true
  try {
    initiatorOptions.value = await listLegalInitiatorOptions('contract')
    rules.initiator_assignment_id[0].required = !isSuperuser.value && initiatorOptions.value.length > 1
    rules.organization_code[0].required = isSuperuser.value
    if (!isEdit.value && dialogVisible.value && initiatorOptions.value.length === 1) {
      const [option] = initiatorOptions.value
      if (isSuperuser.value) onInitiatorOrganizationChange(option.organization_code)
      else onInitiatorAssignmentChange(option.assignment_id)
    }
  } catch {
    initiatorOptions.value = []
    rules.initiator_assignment_id[0].required = false
    rules.organization_code[0].required = false
  } finally {
    initiatorOptionsLoading.value = false
  }
}
function onInitiatorAssignmentChange(assignmentId) {
  const option = initiatorOptions.value.find((item) => Number(item.assignment_id) === Number(assignmentId))
  if (!option) return
  form.initiator_assignment_id = option.assignment_id
  form.party_a = option.company_name || COMPANY_NAMES[option.company_code] || form.party_a
}
function onInitiatorOrganizationChange(organizationCode) {
  const option = initiatorOptions.value.find((item) => item.organization_code === organizationCode)
  if (!option) return
  form.organization_code = option.organization_code
  form.party_a = option.company_name || COMPANY_NAMES[option.company_code] || form.party_a
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
  party_a: '山东出版供应链管理有限公司',
  party_b: '',
  amount: 0,
  currency: '人民币',
  payment_terms: '',
  sign_date: null,
  remark: '',
  attachment_name: '',
  initiator_assignment_id: null,
  organization_code: ''
})
const form = reactive(emptyForm())
const rules = reactive({
  contract_no: [{ required: true, message: '请输入合同编号', trigger: 'blur' }],
  title: [{ required: true, message: '请输入合同名称', trigger: 'blur' }],
  initiator_assignment_id: [{ required: false, message: '请选择发起归属', trigger: 'change' }],
  organization_code: [{ required: false, message: '请选择发起归属', trigger: 'change' }]
})

function openCreate() {
  if (!canOpenCreate.value) return
  isEdit.value = false
  editingId.value = null
  pickedFile.value = null
  Object.assign(form, emptyForm())
  if (initiatorOptions.value.length === 1) {
    const [option] = initiatorOptions.value
    if (isSuperuser.value) onInitiatorOrganizationChange(option.organization_code)
    else onInitiatorAssignmentChange(option.assignment_id)
  }
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
    attachment_name: row.attachment_name || '',
    initiator_assignment_id: null,
    organization_code: ''
  })
  formRef.value?.clearValidate?.()
  dialogVisible.value = true
}
async function onSave() {
  if (!isEdit.value && !canOpenCreate.value) return
  await formRef.value?.validate()
  if (!isEdit.value && !(isSuperuser.value ? form.organization_code : form.initiator_assignment_id)) return
  saving.value = true
  try {
    let contractId = editingId.value
    if (isEdit.value) {
      const { contract_no, attachment_name, initiator_assignment_id, organization_code, ...rest } = form
      await updateContract(editingId.value, { ...rest })
    } else {
      const { attachment_name, initiator_assignment_id, organization_code, ...rest } = form
      const initiator = isSuperuser.value
        ? { organization_code }
        : { initiator_assignment_id }
      const created = await createContract({ ...rest, ...initiator })
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

const submitVisible = ref(false)
const submitSaving = ref(false)
const submitCurrent = ref(null)
const submitPlan = ref(null)
const submitNodes = computed(() => submitPlan.value?.nodes || [])
const submitFieldsRef = ref()
const selectedApprovers = ref({})
let submitPlanRequestGeneration = 0

function isHandlerResubmit(row) {
  return Boolean(row.workflow_instance_id && ['initiator', 'handler'].includes(row.active_task?.node_code))
}

function resetSubmitDialog() {
  submitCurrent.value = null
  submitPlan.value = null
  selectedApprovers.value = {}
}

async function finishSubmit(row, payload) {
  await submitContract(row.id, payload)
  ElMessage.success('已提交审批，合同进入审批流')
  load()
  badgeStore.refresh() // 提交后可能轮到下一环节角色，实时刷新角标
}

async function onSubmit(row) {
  const requestGeneration = ++submitPlanRequestGeneration
  if (isHandlerResubmit(row)) {
    if (submitSaving.value) return
    submitSaving.value = true
    try {
      await finishSubmit(row)
    } finally {
      submitSaving.value = false
    }
    return
  }
  const plan = await getWorkflowSubmissionPlan('contract', row.id)
  if (requestGeneration !== submitPlanRequestGeneration) return
  submitCurrent.value = row
  submitPlan.value = plan
  selectedApprovers.value = {}
  submitVisible.value = true
}

async function confirmSubmit() {
  if (submitSaving.value) return
  submitSaving.value = true
  try {
    if (!await submitFieldsRef.value?.validate()) return
    await finishSubmit(submitCurrent.value, { designated_users: selectedApprovers.value })
    submitVisible.value = false
  } catch (error) {
    if (error.response?.status === 422) {
      await submitFieldsRef.value?.reloadCandidates?.({ preserve: true })
      ElMessage.warning('审批人任职信息已变化，请核对更新后的候选人后重试')
    }
  } finally {
    submitSaving.value = false
  }
}

// 合同审批：通过 / 退回
const actionVisible = ref(false)
const actionSaving = ref(false)
const action = ref('approve')
const actionCurrent = ref(null)
const actionFormRef = ref()
const actionForm = reactive({ comment: '' })
const actionRules = computed(() => ({
  comment: action.value === 'reject'
    ? [{ required: true, message: '请输入退回原因', trigger: 'blur' }]
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
  if (actionSaving.value) return
  actionSaving.value = true
  try {
    await actionFormRef.value?.validate()
    if (action.value === 'approve') {
      await approveContract(actionCurrent.value.id, actionForm.comment)
      ElMessage.success('已通过并附加电子签名')
    } else {
      await rejectContract(actionCurrent.value.id, actionForm.comment)
      ElMessage.success('已退回')
    }
    badgeStore.refresh() // 审批完成后本人待办数减少，实时刷新角标
    actionVisible.value = false
    await load()
  } catch (error) {
    const detail = error.response?.data?.detail
    if (error.response?.status === 409 && detail?.code === 'task_already_completed') {
      actionVisible.value = false
      await load()
      if (detailVisible.value) await detailDrawerRef.value?.reload?.()
      ElMessage.warning(`该节点已由 ${detail.actor || '其他办理人'} 办理`)
      return
    }
    throw error
  } finally {
    actionSaving.value = false
  }
}

// 合同台账
const ledgerVisible = ref(false)
function openLedger() {
  ledgerVisible.value = true
}
async function exportLedger() {
  try {
    const blob = await exportContracts()
    downloadBlob(blob, `合同台账_${new Date().toISOString().slice(0, 10)}.csv`)
    ElMessage.success('合同台账导出成功')
  } catch {
    ElMessage.error('合同台账导出失败，请稍后重试')
  }
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
const detailDrawerRef = ref()
function openDetail(row) {
  detailId.value = row.id
  detailVisible.value = true
}

// AI 合同审查
const aiVisible = ref(false)
const aiLoading = ref(false)
const aiResult = ref(null)
const aiCurrent = ref(null)
const aiHtml = computed(() => renderSafeMarkdown(aiResult.value?.markdown || ''))
const allAiFindings = computed(() => [
  ...(aiResult.value?.fact_checks || []),
  ...(aiResult.value?.risk_findings || [])
])
const coverageRate = computed(() => {
  const value = Number(aiResult.value?.coverage?.evidence_rate)
  if (!Number.isFinite(value)) return '0%'
  return `${Math.round((value > 1 ? value / 100 : value) * 100)}%`
})
const fallbackLabel = computed(() => {
  const labels = {
    not_configured: '未配置 DeepSeek，本次结果由规则引擎生成，请人工复核。',
    provider_error: 'DeepSeek 调用失败，本次结果由规则引擎生成，请人工复核。',
    invalid_response: 'DeepSeek 返回格式无法校验，本次结果由规则引擎生成，请人工复核。',
    no_text: '未提取到合同正文，本次仅依据合同字段核验，请人工复核。'
  }
  return labels[aiResult.value?.fallback_reason] || '本次未使用 DeepSeek，结果由规则引擎生成，请人工复核。'
})
function verdictMeta(verdict) {
  return {
    supported: { label: '有依据', type: 'success' },
    contradicted: { label: '存在矛盾', type: 'danger' },
    not_found: { label: '未找到依据', type: 'warning' },
    not_applicable: { label: '不适用', type: 'info' }
  }[verdict] || { label: '未找到依据', type: 'warning' }
}
function riskMeta(level) {
  return {
    high: { label: '高', type: 'danger' },
    medium: { label: '中', type: 'warning' },
    low: { label: '低', type: 'info' }
  }[level] || { label: '中', type: 'warning' }
}
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

onMounted(() => { load(); loadCustomers(); loadInitiatorOptions() })
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
.cur-role { margin-top: 4px; font-size: 12px; color: var(--el-color-warning); }
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
.upload-tip .picked { color: var(--el-color-success); margin-left: 8px; }
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
.ai-meta-tag, .ai-verdict { display: inline-flex; align-items: center; border: 1px solid var(--el-border-color); border-radius: 4px; padding: 0 7px; min-height: 22px; font-size: 12px; line-height: 20px; }
.ai-meta-tag.is-success, .ai-verdict.is-success { color: var(--el-color-success); border-color: var(--el-color-success-light-5); background: var(--el-color-success-light-9); }
.ai-meta-tag.is-info, .ai-verdict.is-info { color: var(--el-color-info); border-color: var(--el-color-info-light-5); background: var(--el-color-info-light-9); }
.ai-meta-tag.is-primary { color: var(--el-color-primary); border-color: var(--el-color-primary-light-5); background: var(--el-color-primary-light-9); }
.ai-meta-tag.is-warning, .ai-verdict.is-warning { color: var(--el-color-warning); border-color: var(--el-color-warning-light-5); background: var(--el-color-warning-light-9); }
.ai-verdict.is-danger { color: var(--el-color-danger); border-color: var(--el-color-danger-light-5); background: var(--el-color-danger-light-9); }
.ai-risk { font-weight: 500; }
.ai-fallback { margin-bottom: 12px; }
.ai-findings { margin: 4px 0 16px; border: 1px solid var(--el-border-color-lighter); border-radius: 4px; padding: 10px 12px; }
.ai-section-title { color: var(--el-text-color-primary); font-weight: 600; margin-bottom: 8px; }
.ai-finding { padding: 10px 0; border-top: 1px solid var(--el-border-color-lighter); }
.ai-finding:first-of-type { border-top: 0; padding-top: 2px; }
.ai-finding-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ai-claim { flex: 1; min-width: 180px; color: var(--el-text-color-primary); font-weight: 500; }
.ai-finding-line, .ai-quote { margin-top: 5px; color: var(--el-text-color-regular); font-size: 13px; line-height: 1.6; }
.ai-quote { color: var(--el-text-color-secondary); }
.ai-evidence { margin-top: 7px; font-size: 13px; }
.ai-evidence summary { cursor: pointer; color: var(--el-color-primary); user-select: none; }
.ai-evidence-item { margin: 8px 0 0 16px; padding-left: 8px; border-left: 2px solid var(--el-color-primary-light-7); }
.ai-evidence-title { color: var(--el-text-color-primary); font-weight: 500; }
.ai-evidence-text { margin-top: 3px; color: var(--el-text-color-regular); line-height: 1.6; white-space: pre-wrap; }
.ai-not-found { margin-top: 7px; color: var(--el-color-warning); font-size: 12px; }
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
