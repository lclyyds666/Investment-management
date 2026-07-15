<template>
  <el-drawer
    :model-value="modelValue"
    title="合同详情"
    size="820px"
    direction="rtl"
    @update:model-value="(v) => $emit('update:modelValue', v)"
  >
    <div v-loading="loading" v-if="contract">
      <div class="drawer-toolbar">
        <el-tag :type="STATUS_META[contract.status]?.type">
          {{ contract.status_label }}
        </el-tag>
        <el-tag effect="plain">{{ contract.contract_type_label }}</el-tag>
        <span class="flex-1"></span>
        <el-button type="primary" :icon="Printer" @click="doPrint">生成并打印审批单</el-button>
      </div>

      <!-- 基础字段 -->
      <el-descriptions :column="2" border class="mb">
        <el-descriptions-item label="合同编号">{{ contract.contract_no }}</el-descriptions-item>
        <el-descriptions-item label="合同类型">{{ contract.contract_type_label }}</el-descriptions-item>
        <el-descriptions-item label="合同名称" :span="2">{{ contract.title }}</el-descriptions-item>
        <el-descriptions-item label="申请部门">{{ contract.department || '—' }}</el-descriptions-item>
        <el-descriptions-item label="是否内部合同">{{ contract.is_internal ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="合同标的" :span="2">{{ contract.subject || '—' }}</el-descriptions-item>
        <el-descriptions-item label="客户名称">{{ contract.customer_name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="签订日期">{{ contract.sign_date || '—' }}</el-descriptions-item>
        <el-descriptions-item label="合同金额">
          {{ Number(contract.amount).toLocaleString() }} {{ contract.currency || '' }}
          <span class="rmb">（{{ rmb }}）</span>
        </el-descriptions-item>
        <el-descriptions-item label="币种">{{ contract.currency || '—' }}</el-descriptions-item>
        <el-descriptions-item label="付款条件" :span="2">{{ contract.payment_terms || '—' }}</el-descriptions-item>
        <el-descriptions-item label="创建人(业务经办)">{{ contract.creator_name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="当前环节">
          <el-tag v-if="contract.current_role_label" type="warning" size="small">
            {{ contract.current_role_label }}
          </el-tag>
          <span v-else>—</span>
        </el-descriptions-item>
        <el-descriptions-item label="合同附件" :span="2">
          <template v-if="contract.attachment_name">
            <el-icon><Document /></el-icon>
            <span class="att-name">{{ contract.attachment_name }}</span>
            <el-button size="small" link type="primary" @click="downloadAttachment">下载</el-button>
          </template>
          <span v-else>—</span>
        </el-descriptions-item>
        <el-descriptions-item label="备注" :span="2">{{ contract.remark || '无' }}</el-descriptions-item>
      </el-descriptions>

      <!-- 流转进度 -->
      <h4 class="section-title"><el-icon><Guide /></el-icon> 审批流转进度（{{ APPROVAL_CHAIN.length }} 级）</h4>
      <el-steps :active="stepsActive" align-center :process-status="processStatus" finish-status="success" class="chain-steps">
        <el-step v-for="(r, i) in APPROVAL_CHAIN" :key="r" :title="roleLabel(r)" />
      </el-steps>

      <!-- 流转时间轴（审计日志 + 签章） -->
      <h4 class="section-title"><el-icon><Clock /></el-icon> 合规审计日志</h4>
      <el-timeline class="flow-timeline">
        <el-timeline-item
          v-for="a in approvals"
          :key="a.id"
          :type="a.action === 'reject' ? 'danger' : 'success'"
          :timestamp="fmt(a.created_at)"
          size="large"
        >
          <div class="flow-node">
            <div class="flow-node-main">
              <span class="flow-role">{{ a.role_label }}</span>
              <el-tag :type="a.action === 'reject' ? 'danger' : 'success'" size="small" effect="plain">
                {{ a.action === 'reject' ? '驳回' : '通过' }}
              </el-tag>
              <span class="flow-approver">{{ a.approver_name }}</span>
            </div>
            <div class="flow-comment" v-if="a.comment">{{ a.comment }}</div>
            <img v-if="a.signature_snapshot" :src="a.signature_snapshot" class="flow-sig" alt="签名" />
          </div>
        </el-timeline-item>
        <el-empty v-if="!approvals.length" :image-size="60" description="暂无审批流转记录" />
      </el-timeline>
    </div>

    <!-- 打印区：法律文件审批表（@media print 时仅显示此区域） -->
    <teleport to="body">
      <div class="approval-print-root" v-if="contract">
        <div class="print-sheet">
          <div class="print-title">山东出版供应链法律文件审批表</div>
          <table class="print-table legal-table">
            <tbody>
              <tr>
                <th class="lbl">发文单位</th><td>{{ PUBLISHER }}</td>
                <th class="lbl">发文时间</th><td>{{ contract.sign_date || '—' }}</td>
                <th class="lbl">发文人员</th><td>{{ contract.creator_name || '—' }}</td>
              </tr>
              <tr>
                <th class="lbl">文件名称</th><td colspan="5">{{ contract.title }}</td>
              </tr>
              <tr>
                <th class="lbl">合同编号</th><td colspan="5">{{ contract.contract_no }}</td>
              </tr>
              <tr v-for="op in opinionRows" :key="op.role">
                <th class="lbl opinion-lbl">{{ op.label }}</th>
                <td colspan="5" class="opinion-cell">
                  <div class="opinion-body">
                    <span class="opinion-text">{{ opinionText(op.role) }}</span>
                    <img
                      v-if="opinionByRole[op.role]?.signature_snapshot"
                      :src="opinionByRole[op.role].signature_snapshot"
                      class="print-sig"
                      alt="签章"
                    />
                  </div>
                  <div class="opinion-date" v-if="opinionByRole[op.role]">
                    {{ opinionByRole[op.role].approver_name }}　{{ fmtDate(opinionByRole[op.role].created_at) }}
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <div class="print-footer">打印时间：{{ nowText }}　本表由业务平台依据审批流转记录自动生成，签章为电子签名。</div>
        </div>
      </div>
    </teleport>
  </el-drawer>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Printer, Clock, Guide, Document } from '@element-plus/icons-vue'
import { getContract, listApprovals, fetchContractAttachmentBlob } from '@/api/contract'
import { APPROVAL_CHAIN, STATUS_META, ROLES, roleLabel } from '@/constants/business'
import { digitToRMB } from '@/utils/rmb'

// 发文单位固定为「出版供应链」（打印模板要求）
const PUBLISHER = '出版供应链'
// 法律文件审批表的 4 个意见栏（对应审批链上业务经办之后的 4 个节点）
const opinionRows = [
  { role: ROLES.SCM_DIRECTOR, label: '供管公司负责人意见' },
  { role: ROLES.LEGAL_COUNSEL, label: '法律顾问意见' },
  { role: ROLES.RISK_AUDITOR, label: '投资公司法务风控部意见' },
  { role: ROLES.INVEST_DIRECTOR, label: '投资公司分管领导意见' }
]

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  contractId: { type: [Number, String], default: null }
})
defineEmits(['update:modelValue'])

const loading = ref(false)
const contract = ref(null)
const approvals = ref([])
const nowText = ref('')

const rmb = computed(() => (contract.value ? digitToRMB(contract.value.amount) : ''))

// 各审批节点角色 → 该节点最近一次审批记录（用于打印意见栏回填意见+签章）
const opinionByRole = computed(() => {
  const map = {}
  for (const a of approvals.value) map[a.approver_role] = a
  return map
})
function opinionText(role) {
  const a = opinionByRole.value[role]
  if (!a) return ''  // 尚未流转到该节点：留空
  if (a.action === 'reject') return `【驳回】${a.comment || ''}`
  return a.comment || '同意'
}

async function downloadAttachment() {
  if (!contract.value?.attachment_name) return
  try {
    const blob = await fetchContractAttachmentBlob(contract.value.id)
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = contract.value.attachment_name
    a.click()
    URL.revokeObjectURL(a.href)
  } catch {
    ElMessage.error('附件下载失败')
  }
}

const stepsActive = computed(() => {
  const c = contract.value
  if (!c) return 0
  if (c.status === 'approved') return APPROVAL_CHAIN.length
  if (c.status === 'draft') return 0
  return c.current_step // pending / rejected 停留在当前环节
})
const processStatus = computed(() => (contract.value?.status === 'rejected' ? 'error' : 'process'))

function fmt(t) {
  if (!t) return ''
  return String(t).replace('T', ' ').slice(0, 19)
}
function fmtDate(t) {
  if (!t) return ''
  return String(t).slice(0, 10)
}

async function load() {
  if (!props.contractId) return
  loading.value = true
  try {
    const [c, aps] = await Promise.all([
      getContract(props.contractId),
      listApprovals(props.contractId)
    ])
    contract.value = c
    approvals.value = aps
  } finally {
    loading.value = false
  }
}

function doPrint() {
  nowText.value = new Date().toLocaleString('zh-CN')
  nextTick(() => window.print())
}

watch(
  () => [props.modelValue, props.contractId],
  ([visible]) => {
    if (visible && props.contractId) load()
  },
  { immediate: true }
)
</script>

<style scoped lang="scss">
.drawer-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}
.flex-1 { flex: 1; }
.mb { margin-bottom: 8px; }
.rmb { color: #909399; font-size: 12px; }
.att-name { margin: 0 8px 0 4px; }
.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 22px 0 14px;
  font-size: 15px;
  color: #eafcff;
  .el-icon { color: #3f6ad8; }
}
.chain-steps {
  margin-bottom: 8px;
  :deep(.el-step__title) { font-size: 12px; }
}
.flow-timeline {
  padding-left: 4px;
}
.flow-node-main {
  display: flex;
  align-items: center;
  gap: 8px;
}
.flow-role { font-weight: 600; color: #eafcff; }
.flow-approver { color: #a9c2e0; font-size: 13px; }
.flow-comment { margin-top: 4px; color: #909399; font-size: 13px; }
.flow-sig {
  margin-top: 6px;
  height: 44px;
  display: block;
  filter: drop-shadow(0 0 0.5px rgba(0, 0, 0, 0.2));
}
</style>

<!-- 全局打印样式：@media print 时仅显示审批单 -->
<style>
.approval-print-root { display: none; }

@media print {
  body * { visibility: hidden !important; }
  .approval-print-root { display: block !important; position: absolute; left: 0; top: 0; width: 100%; }
  .approval-print-root, .approval-print-root * { visibility: visible !important; }

  @page { size: A4; margin: 16mm; }
}

.print-sheet {
  width: 100%;
  color: #000;
  font-family: 'SimSun', 'Songti SC', serif;
}
.print-title { text-align: center; font-size: 22px; font-weight: 700; letter-spacing: 2px; margin-bottom: 18px; }
.print-subtitle { text-align: center; font-size: 18px; margin: 6px 0 18px; }
.print-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
/* 法律文件审批表：标签列固定宽、意见栏加高留白便于签章 */
.legal-table .lbl {
  width: 110px;
  text-align: center;
  white-space: nowrap;
  font-weight: 700;
}
.legal-table .opinion-lbl { height: 90px; }
.legal-table .opinion-cell { vertical-align: top; }
.legal-table .opinion-body {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  min-height: 70px;
  gap: 12px;
}
.legal-table .opinion-text { flex: 1; line-height: 1.7; white-space: pre-wrap; }
.legal-table .opinion-date { text-align: right; color: #333; font-size: 12px; margin-top: 4px; }
.print-table th,
.print-table td {
  border: 1px solid #000;
  padding: 8px 10px;
  text-align: left;
  vertical-align: middle;
}
.print-table th { background: #f2f2f2; width: 110px; white-space: nowrap; }
.print-remark { min-height: 48px; }
.print-sign-title { margin: 18px 0 8px; font-size: 15px; font-weight: 700; }
.print-sign-table th { text-align: center; width: auto; }
.print-sign-table td { text-align: center; }
.print-sig-cell { height: 46px; }
.print-sig { height: 40px; }
.print-footer { margin-top: 16px; font-size: 12px; color: #333; }
</style>
