<template>
  <div class="hotel-ledger" v-loading="loading">
    <div class="hl-head">
      <div class="hl-title">
        <el-icon><House /></el-icon>
        <span>景区酒店平台核销业务台账</span>
        <el-tag size="small" effect="plain">{{ periodCount }} 期 · {{ savedRows.length }} 行</el-tag>
      </div>
      <div class="hl-ops">
        <el-upload :auto-upload="false" :show-file-list="false" accept=".xlsx,.xls" :on-change="onFileChange">
          <el-button type="primary" :icon="UploadFilled" :loading="parsing">上传对账明细</el-button>
        </el-upload>
        <el-button :icon="Refresh" @click="loadSaved">刷新</el-button>
        <el-button type="success" plain :icon="Download" :disabled="!savedRows.length" @click="onExport">导出Excel</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="hl-tip"
      title="流程：每次上传 1 个对账明细（=1 期，内含抖音/美团/携程等多平台）→ 按平台自动算结算基数（抖音=服务商到账−佣金；美团/携程=平台结算毛额）与间夜 → 录入付款金额（可选）→ 系统算 景区核销=基数×核销率、服务费=间夜×44、结算金额=核销+服务费，并按平台递推景区待核销 → 保存生成台账（按核对日期升序，含本期合计行）。"
    />

    <!-- 待确认区：本期各平台草稿 -->
    <el-card v-if="draftRows.length" shadow="never" class="hl-draft">
      <template #header>
        <div class="draft-header">
          <span><el-icon><EditPen /></el-icon> 待确认台账（本期 {{ draftRows.length }} 平台）—— 抖音可改佣金；各平台可录付款金额/回款</span>
          <div>
            <el-button type="primary" size="small" :icon="Check" :loading="saving" @click="onSave">保存生成台账</el-button>
            <el-button size="small" text @click="draftRows = []">清空草稿</el-button>
          </div>
        </div>
      </template>
      <el-table :data="draftRows" border size="small" class="draft-table">
        <el-table-column label="平台" width="70" prop="platform" />
        <el-table-column label="酒店名称" min-width="180">
          <template #default="{ row }"><el-input v-model="row.hotel_name" size="small" /></template>
        </el-table-column>
        <el-table-column label="核对日期（自动）" width="160" prop="check_date_text" />
        <el-table-column label="间夜" width="90" align="right">
          <template #default="{ row }"><el-input-number v-model="row.room_nights" :min="0" :precision="0" size="small" controls-position="right" style="width:78px" /></template>
        </el-table-column>
        <el-table-column label="结算基数原值" width="130" align="right">
          <template #default="{ row }">{{ fmtMoney(row.base_received) }}</template>
        </el-table-column>
        <el-table-column label="服务商佣金" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.platform === '抖音'" v-model="row.supplier_commission" :min="0" :precision="2" :step="100" size="small" controls-position="right" style="width:120px" />
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="景区核销金额" width="130" align="right">
          <template #default="{ row }"><span class="calc">{{ fmtMoney(rowHexiao(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="景区待核销金额" width="140" align="right">
          <template #default="{ row }"><span class="calc pending">{{ fmtMoney(draftPending(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="付款金额" width="140" align="right">
          <template #default="{ row }"><el-input-number v-model="row.payment_amount" :min="0" :precision="2" :step="1000" size="small" controls-position="right" style="width:120px" /></template>
        </el-table-column>
        <el-table-column label="结算金额（默认可改）" width="160" align="right">
          <template #default="{ row }">
            <el-input-number v-model="row.jinying_amount" :min="0" :precision="2" :step="1000" size="small" controls-position="right" style="width:140px" />
          </template>
        </el-table-column>
        <el-table-column label="服务费" width="110" align="right">
          <template #default="{ row }"><span class="calc">{{ fmtMoney(calcFee(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="回款日期" width="150">
          <template #default="{ row }"><el-date-picker v-model="row.repay_date" type="date" value-format="YYYY-MM-DD" size="small" placeholder="手工" style="width:130px" /></template>
        </el-table-column>
        <el-table-column label="回款金额" width="140" align="right">
          <template #default="{ row }"><el-input-number v-model="row.repay_amount" :min="0" :precision="2" :step="1000" size="small" controls-position="right" style="width:120px" /></template>
        </el-table-column>
      </el-table>
      <div class="draft-note">提示：付款金额仅在此录入（台账中隐藏、数据库留存，参与「景区待核销」按平台递推）。</div>
    </el-card>

    <!-- 已保存台账（按核对日期升序，隐藏付款金额，含本期合计行） -->
    <el-table :data="displayRows" border stripe size="small" class="saved-table" :row-class-name="rowClass">
      <el-table-column label="平台" width="90">
        <template #default="{ row }"><span :class="{ 'total-label': row.isTotal }">{{ row.isTotal ? '本期合计' : row.platform }}</span></template>
      </el-table-column>
      <el-table-column label="酒店名称" min-width="160" show-overflow-tooltip>
        <template #default="{ row }">{{ row.isTotal ? '' : row.hotel_name }}</template>
      </el-table-column>
      <el-table-column label="核对日期" width="160">
        <template #default="{ row }">{{ row.check_date_text }}</template>
      </el-table-column>
      <el-table-column label="景区核销金额" width="130" align="right">
        <template #default="{ row }">{{ fmtMoney(row.hexiao_amount) }}</template>
      </el-table-column>
      <el-table-column label="景区待核销金额" width="140" align="right">
        <template #default="{ row }"><span class="pending">{{ fmtMoney(row.pending_writeoff) }}</span></template>
      </el-table-column>
      <el-table-column label="结算金额" width="130" align="right">
        <template #default="{ row }">{{ fmtMoney(row.jinying_amount) }}</template>
      </el-table-column>
      <el-table-column label="服务费" width="110" align="right">
        <template #default="{ row }">{{ fmtMoney(row.service_fee) }}</template>
      </el-table-column>
      <el-table-column label="间夜" width="80" align="right">
        <template #default="{ row }">{{ row.room_nights }}</template>
      </el-table-column>
      <el-table-column label="回款日期" width="110">
        <template #default="{ row }">{{ row.isTotal ? '' : (row.repay_date || '') }}</template>
      </el-table-column>
      <el-table-column label="回款金额" width="130" align="right">
        <template #default="{ row }">{{ row.isTotal ? fmtMoney(row.repay_amount) : (row.repay_amount != null ? fmtMoney(row.repay_amount) : '—') }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <template v-if="!row.isTotal">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text type="danger" @click="onDeleteRow(row)">删除</el-button>
          </template>
        </template>
      </el-table-column>
      <template #empty>暂无台账，请上传对账明细并保存生成</template>
    </el-table>

    <!-- 编辑单行弹窗 -->
    <el-dialog v-model="editVisible" title="编辑台账行" width="480px">
      <el-form label-width="130px" v-if="editRow">
        <el-form-item label="平台">
          <el-input :model-value="editRow.platform" disabled style="width:100%" />
        </el-form-item>
        <el-form-item label="酒店名称">
          <el-input v-model="editForm.hotel_name" style="width:100%" />
        </el-form-item>
        <el-form-item label="结算基数原值">
          <el-input :model-value="fmtMoney(editRow.base_received)" disabled style="width:100%" />
        </el-form-item>
        <el-form-item v-if="editRow.platform === '抖音'" label="服务商佣金">
          <el-input-number v-model="editForm.supplier_commission" :min="0" :precision="2" :step="100" controls-position="right" style="width:100%" />
        </el-form-item>
        <el-form-item label="间夜">
          <el-input-number v-model="editForm.room_nights" :min="0" :precision="0" controls-position="right" style="width:100%" />
        </el-form-item>
        <el-form-item label="核销率">
          <el-input-number v-model="editForm.ratePctHexiao" :min="0" :max="100" :precision="2" :step="1" controls-position="right" style="width:100%" /><span class="pct-suffix">%</span>
        </el-form-item>
        <el-form-item label="每间夜服务费">
          <el-input-number v-model="editForm.fee_per_night" :min="0" :precision="2" :step="1" controls-position="right" style="width:100%" /><span class="pct-suffix">元</span>
        </el-form-item>
        <el-form-item label="结算金额">
          <el-input-number v-model="editForm.jinying_amount" :min="0" :precision="2" :step="1000" controls-position="right" style="width:100%" />
          <div class="edit-hint">默认 = 景区核销 + 服务费（可手工修改）</div>
        </el-form-item>
        <el-form-item label="付款金额">
          <el-input-number v-model="editForm.payment_amount" :min="0" :precision="2" :step="1000" controls-position="right" style="width:100%" />
        </el-form-item>
        <el-form-item label="回款日期">
          <el-date-picker v-model="editForm.repay_date" type="date" value-format="YYYY-MM-DD" style="width:100%" />
        </el-form-item>
        <el-form-item label="回款金额">
          <el-input-number v-model="editForm.repay_amount" :min="0" :precision="2" :step="1000" controls-position="right" style="width:100%" />
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
import { UploadFilled, Refresh, Download, House, EditPen, Check } from '@element-plus/icons-vue'
import {
  parseHotelFile, getHotelLedger, saveHotelLedger,
  updateHotelRow, deleteHotelRow, fetchHotelLedgerExportBlob
} from '@/api/hotelLedger'
import { downloadBlob } from '@/utils/file'

const props = defineProps({ scenicId: { type: String, required: true } })

const DEFAULT_RATE_HEXIAO = 0.9
const DEFAULT_FEE_PER_NIGHT = 44
const DEFAULT_HOTEL_NAME = '郑和海洋酒店、宝船酒店、水上酒店、长颈鹿酒店'

const loading = ref(false)
const parsing = ref(false)
const saving = ref(false)
const savedRows = ref([])
const draftRows = ref([])

function round2(n) { return Math.round((Number(n) || 0) * 100) / 100 }
function settleBase(row) {
  const comm = row.platform === '抖音' ? (Number(row.supplier_commission) || 0) : 0
  return round2((Number(row.base_received) || 0) - comm)
}
function calcHexiao(row) { return round2(settleBase(row) * DEFAULT_RATE_HEXIAO) }
function calcFee(row) { return round2((Number(row.room_nights) || 0) * DEFAULT_FEE_PER_NIGHT) }
function calcJinying(row) { return round2(calcHexiao(row) + calcFee(row)) }
// 佣金未改 → 展示后端「按日期粒度」精准默认核销；改了 → JS 期级预览(保存时后端按期重算)
function isDefaultComm(row) {
  return Math.abs((Number(row.supplier_commission) || 0) - (Number(row.def_commission) || 0)) < 0.005
}
function rowHexiao(row) { return isDefaultComm(row) ? (Number(row.def_hexiao) || 0) : calcHexiao(row) }

// 各平台已保存末期待核销余额（草稿递推起点）
const lastPendingByPlatform = computed(() => {
  const m = {}
  for (const r of savedRows.value) m[r.platform] = Number(r.pending_writeoff) || 0
  return m
})
function draftPending(row) {
  const base = lastPendingByPlatform.value[row.platform] || 0
  return round2(base + (Number(row.payment_amount) || 0) - rowHexiao(row))
}

function fmtMoney(n) {
  const v = Number(n)
  if (Number.isNaN(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const periodCount = computed(() => new Set(savedRows.value.map((r) => r.check_date_text || r.period_text)).size)

// 展示行：按后端已排序(核对日期升序)分组，每期末尾插入合计行
const displayRows = computed(() => {
  const out = []
  let curKey = null
  let bucket = []
  const flush = () => {
    if (!bucket.length) return
    const t = {
      isTotal: true,
      check_date_text: bucket[0].check_date_text,
      hexiao_amount: 0, pending_writeoff: 0, jinying_amount: 0, service_fee: 0, room_nights: 0, repay_amount: 0
    }
    for (const r of bucket) {
      t.hexiao_amount += Number(r.hexiao_amount) || 0
      t.pending_writeoff += Number(r.pending_writeoff) || 0
      t.jinying_amount += Number(r.jinying_amount) || 0
      t.service_fee += Number(r.service_fee) || 0
      t.room_nights += Number(r.room_nights) || 0
      t.repay_amount += Number(r.repay_amount) || 0
    }
    out.push(...bucket, t)
    bucket = []
  }
  for (const r of savedRows.value) {
    const key = r.check_date_text || r.period_text
    if (curKey !== null && key !== curKey) flush()
    curKey = key
    bucket.push(r)
  }
  flush()
  return out
})
function rowClass({ row }) { return row.isTotal ? 'total-row' : '' }

async function loadSaved() {
  if (!props.scenicId) return
  loading.value = true
  try {
    const res = await getHotelLedger(props.scenicId)
    savedRows.value = res.rows || []
  } finally {
    loading.value = false
  }
}

async function onFileChange(file) {
  const raw = file?.raw
  if (!raw) return
  const name = (raw.name || '').toLowerCase()
  if (!name.endsWith('.xlsx') && !name.endsWith('.xls')) { ElMessage.error('仅支持 Excel 文件(.xlsx/.xls)'); return }
  parsing.value = true
  try {
    const res = await parseHotelFile(props.scenicId, raw)
    ;(res.warnings || []).forEach((w) => ElMessage.warning(w))
    draftRows.value = (res.platforms || []).map((p) => ({
      platform: p.platform,
      hotel_name: DEFAULT_HOTEL_NAME,
      check_date_text: p.check_date_text,
      period_text: p.period_text,
      period_start: p.period_start,
      period_end: p.period_end,
      room_nights: p.room_nights,
      base_received: p.base_received,
      supplier_commission: Number(p.suggested_commission) || 0,
      // 后端「按日期粒度」算出的精准默认值
      def_commission: Number(p.suggested_commission) || 0,
      def_hexiao: Number(p.def_hexiao) || 0,
      def_service_fee: Number(p.def_service_fee) || 0,
      def_jinying: Number(p.def_jinying) || 0,
      // 结算金额默认 = 按日累加精准值，可手工改
      jinying_amount: Number(p.def_jinying) || 0,
      payment_amount: 0,
      repay_date: null,
      repay_amount: null,
      order_count: p.order_count,
      source_file: res.source_file,
      detail_stored: res.detail_stored,
      detail_name: res.detail_name
    }))
    ElMessage.success(`解析完成：本期 ${draftRows.value.length} 个平台`)
  } catch {
    ElMessage.error('解析失败，请检查文件内容')
  } finally {
    parsing.value = false
  }
}

async function onSave() {
  if (!draftRows.value.length) return
  const rows = draftRows.value.map((r) => ({
    platform: r.platform, hotel_name: r.hotel_name,
    check_date_text: r.check_date_text, period_text: r.period_text,
    period_start: r.period_start, period_end: r.period_end,
    room_nights: r.room_nights, base_received: r.base_received,
    supplier_commission: r.supplier_commission || 0,
    rate_hexiao: DEFAULT_RATE_HEXIAO, fee_per_night: DEFAULT_FEE_PER_NIGHT,
    jinying_amount: r.jinying_amount,
    def_commission: r.def_commission,
    def_hexiao: r.def_hexiao,
    def_service_fee: r.def_service_fee,
    def_jinying: r.def_jinying,
    payment_amount: r.payment_amount || 0,
    repay_date: r.repay_date, repay_amount: r.repay_amount,
    order_count: r.order_count, source_file: r.source_file,
    detail_stored: r.detail_stored, detail_name: r.detail_name
  }))
  saving.value = true
  try {
    const res = await saveHotelLedger(props.scenicId, rows, 'append')
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
  hotel_name: '', supplier_commission: 0, room_nights: 0,
  ratePctHexiao: 90, fee_per_night: 44, jinying_amount: 0, payment_amount: 0, repay_date: null, repay_amount: null
})
function openEdit(row) {
  editRow.value = row
  editForm.hotel_name = row.hotel_name
  editForm.supplier_commission = Number(row.supplier_commission) || 0
  editForm.room_nights = Number(row.room_nights) || 0
  editForm.ratePctHexiao = round2((Number(row.rate_hexiao) || DEFAULT_RATE_HEXIAO) * 100)
  editForm.fee_per_night = Number(row.fee_per_night) || DEFAULT_FEE_PER_NIGHT
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
    await updateHotelRow(props.scenicId, editRow.value.id, {
      hotel_name: editForm.hotel_name,
      supplier_commission: editForm.supplier_commission,
      room_nights: editForm.room_nights,
      rate_hexiao: round2(Number(editForm.ratePctHexiao) / 100),
      fee_per_night: editForm.fee_per_night,
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
    await ElMessageBox.confirm(`确定删除该行台账（${row.platform} ${row.check_date_text}）吗？删除后该平台其后各期待核销将自动重算。`, '删除确认', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消'
    })
  } catch { return }
  try {
    await deleteHotelRow(props.scenicId, row.id)
    await loadSaved()
    ElMessage.success('已删除')
  } catch {
    ElMessage.error('删除失败')
  }
}

async function onExport() {
  try {
    const blob = await fetchHotelLedgerExportBlob(props.scenicId)
    downloadBlob(blob, `酒店平台业务台账-${props.scenicId}.xlsx`)
  } catch {
    ElMessage.error('导出失败')
  }
}

watch(() => props.scenicId, loadSaved, { immediate: true })
</script>

<style scoped lang="scss">
.hotel-ledger { margin-top: 6px; }
.hl-head { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-bottom: 10px; }
.hl-title { display: flex; align-items: center; gap: 8px; font-size: 16px; font-weight: 700; color: var(--el-text-color-primary); .el-icon { color: var(--el-color-primary); } }
.hl-ops { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.hl-tip { margin-bottom: 12px; }
.hl-draft { margin-bottom: 16px; border: 1px solid var(--el-color-primary-light-5); }
.draft-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-weight: 600; > div { display: flex; align-items: center; gap: 8px; } }
.draft-table :deep(.el-table__cell) { padding: 4px 0; }
/* 统一所有单元格 + 表头居中对齐 */
.draft-table :deep(.el-table__cell .cell),
.saved-table :deep(.el-table__cell .cell) {
  text-align: center !important;
  justify-content: center;
}
.draft-note { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-hint { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 2px; }
.calc { color: var(--el-color-primary); font-weight: 600; }
.pending { color: #f59e0b; font-weight: 700; }
.muted { color: var(--el-text-color-secondary); }
.saved-table { margin-top: 4px; }
.saved-table :deep(.total-row) { background: var(--el-fill-color-light) !important; font-weight: 700; }
.total-label { font-weight: 700; color: var(--el-color-primary); }
.pct-suffix { margin-left: 6px; color: var(--el-text-color-secondary); }
</style>
