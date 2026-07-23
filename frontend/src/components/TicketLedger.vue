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
          :auto-upload="false" :show-file-list="false" accept=".xlsx,.xls"
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
      title="流程：每次上传 1 个对账明细（即 1 期）→ 自动算「服务商到账」与「服务商佣金(=订单实收×6%−达人−团长，可改)」→ 出版应得到账=服务商到账−服务商佣金 → 录入「付款金额」→ 系统按核销率/服务费率算景区核销(=出版应得×90%)、服务费(=出版应得×4%)、结算金额(=核销+服务费)，并按期次递推「景区待核销金额」→ 保存生成台账。"
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
        <el-table-column label="结算金额（默认可改）" width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              v-model="row.jinying_amount" :min="0" :precision="2" :step="1000"
              size="small" controls-position="right" style="width: 140px"
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
    <el-table :data="savedRows" border stripe size="small" class="saved-table" :show-summary="savedRows.length > 0" :summary-method="summary">
      <el-table-column type="index" label="#" width="46" align="center" />
      <el-table-column label="平台" width="80" prop="platform" />
      <el-table-column label="景区门票" min-width="160" prop="ticket_product" show-overflow-tooltip />
      <el-table-column label="核对日期" width="160" prop="check_date_text" />
      <el-table-column label="景区核销金额" width="130" align="right">
        <template #default="{ row }">{{ fmtMoney(row.hexiao_amount) }}</template>
      </el-table-column>
      <!-- 景区待核销金额：紧邻景区核销金额右侧 -->
      <el-table-column label="景区待核销金额" width="140" align="right">
        <template #default="{ row }"><span class="pending">{{ fmtMoney(row.pending_writeoff) }}</span></template>
      </el-table-column>
      <el-table-column label="结算金额" width="130" align="right">
        <template #default="{ row }">{{ fmtMoney(row.jinying_amount) }}</template>
      </el-table-column>
      <el-table-column label="服务费" width="120" align="right">
        <template #default="{ row }">{{ fmtMoney(row.service_fee) }}</template>
      </el-table-column>
      <el-table-column label="回款日期" width="110" prop="repay_date" />
      <el-table-column label="回款金额" width="130" align="right">
        <template #default="{ row }">{{ row.repay_amount != null ? fmtMoney(row.repay_amount) : '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" text type="danger" @click="onDeleteRow(row)">删除</el-button>
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
        <el-form-item label="服务费率">
          <el-input-number v-model="editForm.ratePctFee" :min="0" :max="100" :precision="2" :step="1" controls-position="right" style="width: 100%" />
          <span class="pct-suffix">%</span>
        </el-form-item>
        <el-form-item label="结算金额">
          <el-input-number v-model="editForm.jinying_amount" :min="0" :precision="2" :step="1000" controls-position="right" style="width: 100%" />
          <div class="edit-hint">默认 = 景区核销 + 服务费（可手工修改）</div>
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
import { ref, computed, watch, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Refresh, Download, Tickets, EditPen, Check } from '@element-plus/icons-vue'
import {
  parseTicketFile, getTicketLedger, saveTicketLedger,
  updateTicketRow, deleteTicketRow, fetchTicketLedgerExportBlob
} from '@/api/ticketLedger'
import { downloadBlob } from '@/utils/file'

const props = defineProps({
  scenicId: { type: String, required: true }
})

const PLATFORMS = ['抖音', '美团', '携程', '同程']
// 默认拆分比例（核销率/服务费率的逐行编辑迁至「编辑台账行」弹窗；草稿按默认值预览）
const DEFAULT_RATE_HEXIAO = 0.9
const DEFAULT_RATE_FEE = 0.04

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
function calcFee(b) { return round2((Number(b) || 0) * DEFAULT_RATE_FEE) }
function calcJinying(b) { return round2(calcHexiao(b) + calcFee(b)) }
// 佣金未改动 → 展示后端「按日期粒度」算出的精准默认值；改动了 → JS 期级预览(保存时后端按期重算)
function isDefaultComm(row) {
  return Math.abs((Number(row.supplier_commission) || 0) - (Number(row.def_commission) || 0)) < 0.005
}
function rowHexiao(row) {
  return isDefaultComm(row) ? (Number(row.def_hexiao) || 0) : calcHexiao(draftPublisherDue(row))
}
function rowFee(row) {
  return isDefaultComm(row) ? (Number(row.def_service_fee) || 0) : calcFee(draftPublisherDue(row))
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
      // 结算金额默认 = 按日累加的精准值，可手工改
      jinying_amount: Number(f.def_jinying) || 0,
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
    rate_fee: DEFAULT_RATE_FEE,
    jinying_amount: r.jinying_amount,
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
  ratePctHexiao: 90, ratePctFee: 4, jinying_amount: 0, payment_amount: 0,
  repay_date: null, repay_amount: null
})

const editPublisherDue = computed(() => {
  if (!editRow.value) return 0
  return round2((Number(editRow.value.supplier_received) || 0) - (Number(editForm.supplier_commission) || 0))
})

function openEdit(row) {
  editRow.value = row
  editForm.pay_date = row.pay_date
  editForm.platform = row.platform
  editForm.supplier_commission = Number(row.supplier_commission) || 0
  editForm.ratePctHexiao = round2((Number(row.rate_hexiao) || DEFAULT_RATE_HEXIAO) * 100)
  editForm.ratePctFee = round2((Number(row.rate_fee) || DEFAULT_RATE_FEE) * 100)
  editForm.jinying_amount = Number(row.jinying_amount) || 0
  editForm.payment_amount = Number(row.payment_amount) || 0
  editForm.repay_date = row.repay_date
  editForm.repay_amount = row.repay_amount != null ? Number(row.repay_amount) : null
  editVisible.value = true
}

async function onSaveEdit() {
  if (!editRow.value) return
  savingEdit.value = true
  try {
    await updateTicketRow(props.scenicId, editRow.value.id, {
      pay_date: editForm.pay_date,
      platform: editForm.platform,
      supplier_commission: editForm.supplier_commission,
      rate_hexiao: round2(Number(editForm.ratePctHexiao) / 100),
      rate_fee: round2(Number(editForm.ratePctFee) / 100),
      jinying_amount: editForm.jinying_amount,
      payment_amount: editForm.payment_amount,
      repay_date: editForm.repay_date,
      repay_amount: editForm.repay_amount
    })
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

// el-table 合计行（列序：# 平台 景区门票 核对日期 景区核销 景区待核销 结算金额 服务费 回款日期 回款金额 操作）
function summary({ columns, data }) {
  const sums = []
  const sumCols = { 4: 'hexiao_amount', 6: 'jinying_amount', 7: 'service_fee', 9: 'repay_amount' }
  columns.forEach((col, idx) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    // 景区待核销为滚动余额 → 取末期值
    if (idx === 5) {
      sums[idx] = data.length ? fmtMoney(data[data.length - 1].pending_writeoff) : ''
      return
    }
    const key = sumCols[idx]
    if (key) {
      const total = data.reduce((acc, r) => acc + (Number(r[key]) || 0), 0)
      sums[idx] = fmtMoney(total)
    } else {
      sums[idx] = ''
    }
  })
  return sums
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

.edit-hint { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 2px; }
.pct-suffix { margin-left: 6px; color: var(--el-text-color-secondary); }
</style>
