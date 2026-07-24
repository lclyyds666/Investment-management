<template>
  <div class="ticket-ledger" v-loading="loading">
    <!-- 顶部：标题 + 操作（核销率/服务费率已迁至「编辑台账行」弹窗集中编辑） -->
    <div class="tl-head">
      <div class="tl-title">
        <el-icon><Tickets /></el-icon>
        <span>景区门票核销台账</span>
        <el-tag size="small" effect="plain">共 {{ savedRows.length }} 期</el-tag>
      </div>
      <div class="tl-ops">
        <el-upload
          v-if="canEdit" :auto-upload="false" :show-file-list="false" accept=".xlsx,.xls"
          :on-change="onFileChange"
        >
          <el-button type="primary" :icon="UploadFilled" :loading="parsing">上传对账明细</el-button>
        </el-upload>
        <el-button :icon="Refresh" @click="loadSaved">刷新</el-button>
        <el-button
          type="success" plain :icon="Download"
          :disabled="!savedRows.length" @click="onExport"
        >导出Excel</el-button>
      </div>
    </div>

    <el-alert
      type="info" :closable="false" show-icon class="tl-tip"
      title="流程：每次上传 1 个对账明细（即 1 期）→ 自动算「服务商到账」与「服务商佣金(=订单实收×6%−达人−团长，可改)」→ 出版应得到账=服务商到账−服务商佣金 → 录入「付款金额」→ 系统按核销率/结算费率算景区核销(=出版应得×90%)、结算金额(=出版应得×结算费率94%)、服务费(=结算−核销)，并按期次递推「景区待核销金额」→ 保存生成台账。"
    />

    <!-- 待确认区：本期上传解析后的可编辑草稿表（仅展示本次上传，不含历史已确认记录） -->
    <el-card v-if="draftRows.length" shadow="never" class="tl-draft">
      <template #header>
        <div class="draft-header">
          <span><el-icon><EditPen /></el-icon> 待确认台账（本期）—— 请录入「服务商佣金」与「付款金额」</span>
          <div>
            <el-button type="primary" size="small" :icon="Check" :loading="saving" @click="onSave">保存生成台账</el-button>
            <el-button size="small" text @click="clearDraft">清空草稿</el-button>
          </div>
        </div>
      </template>

      <el-table :data="draftRows" border size="small" class="draft-table">
        <el-table-column label="付款日期" width="150">
          <template #default="{ row }">
            <el-date-picker v-model="row.pay_date" type="date" value-format="YYYY-MM-DD" size="small" placeholder="手工选择" style="width: 130px" />
          </template>
        </el-table-column>
        <el-table-column label="平台" width="110">
          <template #default="{ row }">
            <el-select v-model="row.platform" size="small" placeholder="选择" style="width: 92px">
              <el-option v-for="p in PLATFORMS" :key="p" :label="p" :value="p" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="景区门票" min-width="180">
          <template #default="{ row }">
            <el-input v-model="row.ticket_product" size="small" />
          </template>
        </el-table-column>
        <el-table-column label="核对日期（自动）" width="170" prop="check_date_text" />
        <el-table-column label="服务商到账（自动）" width="140" align="right">
          <template #default="{ row }">{{ fmtMoney(row.supplier_received) }}</template>
        </el-table-column>
        <el-table-column label="服务商佣金(自动·可改)" width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.supplier_commission" :min="0" :precision="2" :step="100"
              size="small" controls-position="right" style="width: 130px"
              @change="onDraftCommChange(row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="出版应得到账金额" width="150" align="right">
          <template #default="{ row }">
            <span class="calc">{{ fmtMoney(draftPublisherDue(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="景区核销金额" width="130" align="right">
          <template #default="{ row }">
            <span class="calc">{{ fmtMoney(rowHexiao(row)) }}</span>
          </template>
        </el-table-column>
        <!-- 景区待核销金额：紧邻景区核销金额右侧；按期次递推预览 -->
        <el-table-column label="景区待核销金额" width="140" align="right">
          <template #default="{ row }">
            <span class="calc pending">{{ fmtMoney(draftPending(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="付款金额 ★" width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.payment_amount" :min="0" :precision="2" :step="1000"
              size="small" controls-position="right" style="width: 130px"
            />
          </template>
        </el-table-column>
        <el-table-column label="结算金额（可改）" width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.jinying_amount" :min="0" :precision="2" :step="1000"
              size="small" controls-position="right" style="width: 140px"
              @change="row.jinyingEdited = true"
            />
          </template>
        </el-table-column>
        <el-table-column label="服务费" width="120" align="right">
          <template #default="{ row }">
            <span class="calc">{{ fmtMoney(rowFee(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="回款日期" width="150">
          <template #default="{ row }">
            <el-date-picker v-model="row.repay_date" type="date" value-format="YYYY-MM-DD" size="small" placeholder="手工" style="width: 130px" />
          </template>
        </el-table-column>
        <el-table-column label="回款金额" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.repay_amount" :min="0" :precision="2" :step="1000" size="small" controls-position="right" style="width: 120px" />
          </template>
        </el-table-column>
        <el-table-column label="来源文件" min-width="200" prop="source_file" show-overflow-tooltip />
      </el-table>
    </el-card>

    <!-- 已保存台账（景区核销数据台账；已隐藏「付款日期」列，字段仍保留于数据库） -->
    <el-table :data="displayRows" border stripe size="small" class="saved-table" :row-class-name="rowClass">
      <el-table-column label="景区ID" width="150" fixed="left">
        <template #default="{ row }">{{ row.isTotal ? '' : scenicName }}</template>
      </el-table-column>
      <el-table-column label="平台" width="90">
        <template #default="{ row }"><span :class="{ 'total-label': row.isTotal }">{{ row.isTotal ? '本期合计' : row.platform }}</span></template>
      </el-table-column>
      <el-table-column label="景区门票" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ row.isTotal ? '' : row.ticket_product }}</template>
      </el-table-column>
      <el-table-column label="核对日期" width="160" prop="check_date_text" />
      <el-table-column label="景区核销金额" width="130" align="right">
        <template #default="{ row }">{{ fmtMoney(row.hexiao_amount) }}</template>
      </el-table-column>
      <!-- 景区待核销金额：本期合计行(多行)或独行(单行)显示 -->
      <el-table-column label="景区待核销金额" width="140" align="right">
        <template #default="{ row }"><span v-if="row.isTotal || row.isSoloPeriod" class="pending">{{ fmtMoney(row.pending_writeoff) }}</span></template>
      </el-table-column>
      <el-table-column label="结算金额" width="130" align="right">
        <template #default="{ row }">{{ fmtMoney(row.jinying_amount) }}</template>
      </el-table-column>
      <el-table-column label="服务费" width="120" align="right">
        <template #default="{ row }">{{ fmtMoney(row.service_fee) }}</template>
      </el-table-column>
      <el-table-column label="回款日期" width="110">
        <template #default="{ row }">{{ (row.isTotal || row.isSoloPeriod) ? (row.repay_date || '') : '' }}</template>
      </el-table-column>
      <el-table-column label="回款金额" width="130" align="right">
        <template #default="{ row }">{{ (row.isTotal || row.isSoloPeriod) ? (row.repay_amount != null ? fmtMoney(row.repay_amount) : '—') : '' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <template v-if="!row.isTotal && canEdit">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text type="danger" @click="onDeleteRow(row)">删除</el-button>
          </template>
        </template>
      </el-table-column>
      <!-- 状态：本期合计行(多行)或独行(单行)有内容；确认函仅业务复核+信息维护 -->
      <el-table-column label="状态" width="250" fixed="right">
        <template #default="{ row }">
          <template v-if="row.isTotal || row.isSoloPeriod">
            <template v-if="row.confirm_stored">
              <el-tag type="success" size="small" effect="plain">已确认</el-tag>
              <template v-if="canConfirm">
                <el-button size="small" text type="primary" @click="onConfirmView(row)">查看</el-button>
                <el-button size="small" text @click="onConfirmDownload(row)">下载</el-button>
                <el-button size="small" text type="danger" @click="onConfirmDelete(row)">删除</el-button>
              </template>
            </template>
            <template v-else>
              <el-tag type="info" size="small" effect="plain">未确认</el-tag>
              <el-upload
                v-if="canConfirm" :auto-upload="false" :show-file-list="false"
                accept=".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx"
                :on-change="(f) => onConfirmPick(row, f)"
                style="display:inline-block; margin-left:8px"
              >
                <el-button size="small" text type="primary">上传确认函</el-button>
              </el-upload>
            </template>
          </template>
        </template>
      </el-table-column>
      <template #empty>暂无台账，请上传对账明细并保存生成</template>
    </el-table>

    <!-- 编辑单行弹窗（集中编辑：服务商佣金 / 核销率 / 服务费率 / 付款金额 / 回款） -->
    <el-dialog v-model="editVisible" title="编辑台账行" width="480px">
      <el-form label-width="120px" v-if="editRow">
        <el-form-item label="付款日期">
          <el-date-picker v-model="editForm.pay_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="平台">
          <el-select v-model="editForm.platform" style="width: 100%">
            <el-option v-for="p in PLATFORMS" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="服务商到账">
          <el-input :model-value="fmtMoney(editRow.supplier_received)" disabled style="width: 100%" />
        </el-form-item>
        <el-form-item label="服务商佣金">
          <el-input-number v-model="editForm.supplier_commission" :min="0" :precision="2" :step="100" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="出版应得到账">
          <el-input :model-value="fmtMoney(editPublisherDue)" disabled style="width: 100%" />
          <div class="edit-hint">出版应得到账 = 服务商到账 − 服务商佣金（自动）</div>
        </el-form-item>
        <el-form-item label="核销率">
          <el-input-number v-model="editForm.ratePctHexiao" :min="0" :max="100" :precision="2" :step="1" controls-position="right" style="width: 100%" />
          <span class="pct-suffix">%</span>
        </el-form-item>
        <el-form-item label="结算费率">
          <el-input-number v-model="editForm.ratePctSettle" :min="0" :max="100" :precision="2" :step="1" controls-position="right" style="width: 100%" />
          <span class="pct-suffix">%</span>
        </el-form-item>
        <el-form-item label="结算金额">
          <el-input-number v-model="editForm.jinying_amount" :min="0" :precision="2" :step="1000" controls-position="right" style="width: 100%" @change="editForm.jinyingEdited = true" />
          <div class="edit-hint">默认 = 出版应得 × 结算费率（改佣金/费率自动跟随、逐日累加）；可手工改，服务费 = 结算 − 核销</div>
        </el-form-item>
        <el-form-item label="付款金额">
          <el-input-number v-model="editForm.payment_amount" :min="0" :precision="2" :step="1000" controls-position="right" style="width: 100%" />
        </el-form-item>
        <el-form-item label="回款日期">
          <el-date-picker v-model="editForm.repay_date" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
        </el-form-item>
        <el-form-item label="回款金额">
          <el-input-number v-model="editForm.repay_amount" :min="0" :precision="2" :step="1000" controls-position="right" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingEdit" @click="onSaveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, reactive, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Refresh, Download, Tickets, EditPen, Check } from '@element-plus/icons-vue'
import {
  parseTicketFile, getTicketLedger, saveTicketLedger,
  updateTicketRow, deleteTicketRow, fetchTicketLedgerExportBlob,
  uploadTicketConfirm, deleteTicketConfirm, fetchTicketConfirmBlob
} from '@/api/ticketLedger'
import { downloadBlob } from '@/utils/file'
import { getScenicById } from '@/constants/scenic'
import { ROLES } from '@/constants/business'
import { useUserStore } from '@/store/user'

const props = defineProps({
  scenicId: { type: String, required: true }
})

const userStore = useUserStore()
// 景区ID = 景区名（与客户档案「客户ID」内容一致，作为关联键）
const scenicName = computed(() => getScenicById(props.scenicId)?.name || props.scenicId)
// 上传/编辑/删除台账：业务经办 + 信息维护(超管)
const canEdit = computed(() => userStore.isSuperuser || userStore.role === ROLES.BUSINESS_HANDLER)
// 确认函上传/查看/下载/删除：业务复核 + 信息维护(超管)
const canConfirm = computed(() => userStore.isSuperuser || userStore.role === ROLES.BUSINESS_REVIEWER)

const PLATFORMS = ['抖音', '美团', '携程', '同程']
// 默认比例（核销率/结算费率的逐行编辑迁至「编辑台账行」弹窗；草稿按默认值预览）
// 结算费率默认 0.94（= 旧核销率0.90 + 旧服务费率0.04）：结算金额=出版应得×结算费率，服务费=结算−核销。
const DEFAULT_RATE_HEXIAO = 0.9
const DEFAULT_RATE_SETTLE = 0.94

const loading = ref(false)
const parsing = ref(false)
const saving = ref(false)
const savedRows = ref([])
const draftRows = ref([])

function round2(n) {
  return Math.round((Number(n) || 0) * 100) / 100
}
// 出版应得到账 = 服务商到账 − 服务商佣金
function draftPublisherDue(row) {
  return round2((Number(row.supplier_received) || 0) - (Number(row.supplier_commission) || 0))
}
function calcHexiao(b) { return round2((Number(b) || 0) * DEFAULT_RATE_HEXIAO) }
function calcJinying(b) { return round2((Number(b) || 0) * DEFAULT_RATE_SETTLE) }
function calcFee(b) { return round2(calcJinying(b) - calcHexiao(b)) }
// 佣金未改动 → 展示后端「按日期粒度」算出的精准默认值；改动了 → JS 期级预览(保存时后端按期重算)
function isDefaultComm(row) {
  return Math.abs((Number(row.supplier_commission) || 0) - (Number(row.def_commission) || 0)) < 0.005
}
function rowHexiao(row) {
  return isDefaultComm(row) ? (Number(row.def_hexiao) || 0) : calcHexiao(draftPublisherDue(row))
}
// 结算金额默认值：佣金未改用后端「逐日累加」值，改了用 JS 期级预览(保存后按逐日重算)
function rowJinyingDefault(row) {
  return isDefaultComm(row) ? (Number(row.def_jinying) || 0) : calcJinying(draftPublisherDue(row))
}
// 改服务商佣金 → 结算金额回到默认(跟随)，清除手工标记
function onDraftCommChange(row) {
  row.jinying_amount = rowJinyingDefault(row)
  row.jinyingEdited = false
}
// 服务费 = 结算金额 − 景区核销金额（结算金额可手工改）
function rowFee(row) {
  return round2((Number(row.jinying_amount) || 0) - rowHexiao(row))
}

// 已保存台账末期滚动余额（新一期递推起点）
const lastSavedPending = computed(() => {
  const n = savedRows.value.length
  return n ? (Number(savedRows.value[n - 1].pending_writeoff) || 0) : 0
})
// 草稿期景区待核销金额预览：上期余额 + 本期付款 − 本期核销
function draftPending(row) {
  const hexiao = rowHexiao(row)
  return round2(lastSavedPending.value + (Number(row.payment_amount) || 0) - hexiao)
}

function fmtMoney(n) {
  const v = Number(n)
  if (Number.isNaN(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function loadSaved() {
  if (!props.scenicId) return
  loading.value = true
  try {
    const res = await getTicketLedger(props.scenicId)
    savedRows.value = res.rows || []
  } finally {
    loading.value = false
  }
}

function clearDraft() {
  draftRows.value = []
}

async function onFileChange(file) {
  // 单文件=一期：每次仅取本次选择的文件，替换旧草稿（仅展示本次上传）
  const raw = file?.raw
  if (!raw) return
  const name = (raw.name || '').toLowerCase()
  if (!name.endsWith('.xlsx') && !name.endsWith('.xls')) {
    ElMessage.error('仅支持 Excel 文件(.xlsx/.xls)')
    return
  }
  parsing.value = true
  try {
    const res = await parseTicketFile(props.scenicId, raw)
    ;(res.warnings || []).forEach((w) => ElMessage.warning(w))
    // 本次上传仅生成本期一条待确认记录，替换旧草稿
    draftRows.value = (res.files || []).map((f) => ({
      pay_date: null,
      platform: '抖音',
      ticket_product: f.ticket_product || '水上世界/童话世界/海洋王国',
      check_date_text: f.check_date_text,
      period_text: f.period_text,
      period_start: f.period_start,
      period_end: f.period_end,
      supplier_received: f.supplier_received,
      // 服务商佣金 = 订单实收×6% − 达人 − 团长（后端按日算出的建议值，可手工修改）
      supplier_commission: Number(f.suggested_commission) || 0,
      // 后端「按日期粒度」算出的精准默认值（未改佣金时直接展示/采用）
      def_commission: Number(f.suggested_commission) || 0,
      def_hexiao: Number(f.def_hexiao) || 0,
      def_service_fee: Number(f.def_service_fee) || 0,
      def_jinying: Number(f.def_jinying) || 0,
      // 逐日明细透传持久化（编辑改费率/佣金时后端按天重算）
      daily_json: f.daily_json || '',
      // 结算金额默认=逐日累加值，可手工改；jinyingEdited 标记是否被手工改过
      jinying_amount: Number(f.def_jinying) || 0,
      jinyingEdited: false,
      payment_amount: 0,
      order_count: f.order_count,
      repay_date: null,
      repay_amount: null,
      source_file: f.source_file,
      detail_stored: f.detail_stored,
      detail_name: f.detail_name
    }))
    ElMessage.success('解析完成（本期），请录入「服务商佣金」与「付款金额」后保存。')
  } catch {
    ElMessage.error('解析失败，请检查文件内容')
  } finally {
    parsing.value = false
  }
}

async function onSave() {
  if (!draftRows.value.length) return
  const rows = draftRows.value.map((r) => ({
    pay_date: r.pay_date,
    platform: r.platform,
    ticket_product: r.ticket_product,
    check_date_text: r.check_date_text,
    period_text: r.period_text,
    period_start: r.period_start,
    period_end: r.period_end,
    supplier_received: r.supplier_received,
    supplier_commission: r.supplier_commission || 0,
    payment_amount: r.payment_amount || 0,
    rate_hexiao: DEFAULT_RATE_HEXIAO,
    rate_settle: DEFAULT_RATE_SETTLE,
    daily_json: r.daily_json,
    // 结算金额仅在手工改过时上传(覆盖)，否则由后端逐日累加
    jinying_amount: r.jinyingEdited ? r.jinying_amount : null,
    def_commission: r.def_commission,
    def_hexiao: r.def_hexiao,
    def_service_fee: r.def_service_fee,
    def_jinying: r.def_jinying,
    order_count: r.order_count,
    repay_date: r.repay_date,
    repay_amount: r.repay_amount,
    source_file: r.source_file,
    detail_stored: r.detail_stored,
    detail_name: r.detail_name
  }))
  saving.value = true
  try {
    // 单期上传恒为追加（后端会集中重算滚动余额）
    const res = await saveTicketLedger(props.scenicId, rows, 'append')
    savedRows.value = res.rows || []
    draftRows.value = []
    ElMessage.success('已保存生成台账')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

// —— 编辑单行 ——
const editVisible = ref(false)
const editRow = ref(null)
const savingEdit = ref(false)
const editForm = reactive({
  pay_date: null, platform: '', supplier_commission: 0,
  ratePctHexiao: 90, ratePctSettle: 94, jinying_amount: 0, jinyingEdited: false, payment_amount: 0,
  repay_date: null, repay_amount: null
})

const editPublisherDue = computed(() => {
  if (!editRow.value) return 0
  return round2((Number(editRow.value.supplier_received) || 0) - (Number(editForm.supplier_commission) || 0))
})
// 结算金额默认值 = 出版应得 × 结算费率；保存后由后端按逐日累加得精确值
const editJinying = computed(() => round2(editPublisherDue.value * (Number(editForm.ratePctSettle) || 0) / 100))
// 改佣金/费率 → 结算金额回到默认(跟随)并清手工标记；openEdit 期间抑制，避免冲掉已存值
let suppressJinyingWatch = false
watch(
  () => [editForm.supplier_commission, editForm.ratePctHexiao, editForm.ratePctSettle],
  () => {
    if (suppressJinyingWatch) return
    editForm.jinying_amount = editJinying.value
    editForm.jinyingEdited = false
  }
)

function openEdit(row) {
  suppressJinyingWatch = true   // 载入既有值期间不触发跟随
  editRow.value = row
  editForm.pay_date = row.pay_date
  editForm.platform = row.platform
  editForm.supplier_commission = Number(row.supplier_commission) || 0
  editForm.ratePctHexiao = round2((Number(row.rate_hexiao) || DEFAULT_RATE_HEXIAO) * 100)
  editForm.ratePctSettle = round2((Number(row.rate_settle) || DEFAULT_RATE_SETTLE) * 100)
  editForm.jinying_amount = Number(row.jinying_amount) || 0
  editForm.jinyingEdited = false
  editForm.payment_amount = Number(row.payment_amount) || 0
  editForm.repay_date = row.repay_date
  editForm.repay_amount = row.repay_amount != null ? Number(row.repay_amount) : null
  editVisible.value = true
  nextTick(() => { suppressJinyingWatch = false })
}

async function onSaveEdit() {
  if (!editRow.value) return
  savingEdit.value = true
  try {
    const payload = {
      pay_date: editForm.pay_date,
      platform: editForm.platform,
      supplier_commission: editForm.supplier_commission,
      rate_hexiao: round2(Number(editForm.ratePctHexiao) / 100),
      rate_settle: round2(Number(editForm.ratePctSettle) / 100),
      payment_amount: editForm.payment_amount,
      repay_date: editForm.repay_date,
      repay_amount: editForm.repay_amount
    }
    // 仅当手工改过结算金额才上传覆盖，否则由后端逐日累加
    if (editForm.jinyingEdited) payload.jinying_amount = editForm.jinying_amount
    await updateTicketRow(props.scenicId, editRow.value.id, payload)
    editVisible.value = false
    await loadSaved()
    ElMessage.success('已更新')
  } catch {
    ElMessage.error('更新失败')
  } finally {
    savingEdit.value = false
  }
}

async function onDeleteRow(row) {
  try {
    await ElMessageBox.confirm(`确定删除该期台账（${row.check_date_text || row.id}）吗？删除后其后各期待核销余额将自动重算。`, '删除确认', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消'
    })
  } catch { return }
  try {
    await deleteTicketRow(props.scenicId, row.id)
    await loadSaved()
    ElMessage.success('已删除')
  } catch {
    ElMessage.error('删除失败')
  }
}

async function onExport() {
  try {
    const blob = await fetchTicketLedgerExportBlob(props.scenicId)
    downloadBlob(blob, `业务台账-${props.scenicId}.xlsx`)
  } catch {
    ElMessage.error('导出失败')
  }
}

// 展示行：按「一份对账明细=一期」分组（对齐酒店台账）。
//  · 一期 ≥2 行 → 追加「本期合计」行(承载待核销/回款/状态)；
//  · 一期只有 1 行 → 该行自身承载期级信息(isSoloPeriod)，不生成合计行。
const displayRows = computed(() => {
  const groups = new Map()
  for (const r of savedRows.value) {
    const key = r.source_file || r.detail_name || r.period_text || r.check_date_text || 'NA'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(r)
  }
  const buckets = [...groups.values()].map((rows) => {
    const minStart = rows.map((r) => r.period_start).filter(Boolean).sort()[0] || ''
    return { rows, minStart }
  })
  buckets.sort((a, b) => String(a.minStart).localeCompare(String(b.minStart)))
  const out = []
  for (const b of buckets) {
    if (b.rows.length < 2) {
      const r0 = b.rows[0]
      out.push({ ...r0, isSoloPeriod: true, period_row_id: r0.id })
      continue
    }
    const t = {
      isTotal: true, platform: '本期合计', ticket_product: '',
      check_date_text: b.rows[0].check_date_text || '',
      hexiao_amount: 0, jinying_amount: 0, service_fee: 0, pending_writeoff: 0,
      repay_date: '', repay_amount: null
    }
    for (const r of b.rows) {
      t.hexiao_amount += Number(r.hexiao_amount) || 0
      t.jinying_amount += Number(r.jinying_amount) || 0
      t.service_fee += Number(r.service_fee) || 0
      t.repay_amount = (t.repay_amount || 0) + (Number(r.repay_amount) || 0)
    }
    // 待核销为滚动余额 → 取本期末行值；回款日期取本期首个非空
    t.pending_writeoff = Number(b.rows[b.rows.length - 1]?.pending_writeoff) || 0
    t.repay_date = (b.rows.find((r) => r.repay_date) || {}).repay_date || ''
    t.period_row_id = b.rows[0]?.id
    t.confirm_stored = b.rows[0]?.confirm_stored || ''
    t.confirm_name = b.rows[0]?.confirm_name || ''
    out.push(...b.rows, t)
  }
  return out
})
function rowClass({ row }) { return row.isTotal ? 'total-row' : '' }

// —— 本期确认函（业务复核/信息维护）——
async function onConfirmPick(row, file) {
  const raw = file?.raw
  if (!raw) return
  try {
    await uploadTicketConfirm(props.scenicId, row.period_row_id, raw)
    ElMessage.success('确认函已上传，本期状态：已确认')
    await loadSaved()
  } catch {
    ElMessage.error('确认函上传失败')
  }
}
async function onConfirmView(row) {
  try {
    const blob = await fetchTicketConfirmBlob(props.scenicId, row.confirm_stored, row.confirm_name)
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch {
    ElMessage.error('查看失败')
  }
}
async function onConfirmDownload(row) {
  try {
    const blob = await fetchTicketConfirmBlob(props.scenicId, row.confirm_stored, row.confirm_name)
    downloadBlob(blob, row.confirm_name || '确认函')
  } catch {
    ElMessage.error('下载失败')
  }
}
async function onConfirmDelete(row) {
  try {
    await ElMessageBox.confirm('确定删除本期确认函吗？删除后本期状态变为「未确认」。', '删除确认', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消'
    })
  } catch { return }
  try {
    await deleteTicketConfirm(props.scenicId, row.period_row_id)
    ElMessage.success('确认函已删除，本期状态：未确认')
    await loadSaved()
  } catch {
    ElMessage.error('删除失败')
  }
}

watch(() => props.scenicId, loadSaved, { immediate: true })
</script>

<style scoped lang="scss">
.ticket-ledger { margin-top: 6px; }
.tl-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 10px;
}
.tl-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 700;
  color: var(--el-text-color-primary);
  .el-icon { color: var(--el-color-primary); }
}
.tl-ops { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.tl-tip { margin-bottom: 12px; }
.tl-draft { margin-bottom: 16px; border: 1px solid var(--el-color-primary-light-5); }
.draft-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  font-weight: 600;
  > div { display: flex; align-items: center; gap: 8px; }
}
.draft-table :deep(.el-table__cell) { padding: 4px 0; }
/* 统一所有单元格 + 表头居中对齐 */
.draft-table :deep(.el-table__cell .cell),
.saved-table :deep(.el-table__cell .cell) {
  text-align: center !important;
  justify-content: center;
}
.calc { color: var(--el-color-primary); font-weight: 600; }
.pending { color: #f59e0b; font-weight: 700; }
.saved-table { margin-top: 4px; }
.saved-table :deep(.total-row) { background: var(--el-fill-color-light) !important; font-weight: 700; }
.total-label { font-weight: 700; color: var(--el-color-primary); }

.edit-hint { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 2px; }
.pct-suffix { margin-left: 6px; color: var(--el-text-color-secondary); }
</style>
