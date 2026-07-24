<template>
  <div class="hotel-ledger" v-loading="loading">
    <div class="hl-head">
      <div class="hl-title">
        <el-icon><House /></el-icon>
        <span>景区酒店核销台账</span>
        <el-tag size="small" effect="plain">{{ periodCount }} 期 · {{ savedRows.length }} 行</el-tag>
      </div>
      <div class="hl-ops">
        <el-upload v-if="canEdit" :auto-upload="false" :show-file-list="false" accept=".xlsx,.xls" :on-change="onFileChange">
          <el-button type="primary" :icon="UploadFilled" :loading="parsing">上传对账明细</el-button>
        </el-upload>
        <el-button :icon="Refresh" @click="loadSaved">刷新</el-button>
        <el-button type="success" plain :icon="Download" :disabled="!savedRows.length" @click="onExport">导出Excel</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="hl-tip"
      title="流程：每次上传 1 个对账明细（=1 期，内含抖音/美团/携程等多平台）→ 按平台自动算结算基数（抖音=服务商到账−佣金；美团/携程=平台结算毛额）与间夜 → 录入付款金额/回款（本期各平台共享）→ 系统算 景区核销=基数×核销率、结算金额与服务费（默认算法1：服务费=间夜×44、结算=核销+服务费；可在「编辑台账行」切换算法2：结算=基数×结算费率、服务费=结算−核销），并按整期递推景区待核销 → 保存生成台账（按核对日期升序，含本期合计行）。"
    />

    <!-- 待确认区：本期各平台草稿 -->
    <el-card v-if="draftRows.length" shadow="never" class="hl-draft">
      <template #header>
        <div class="draft-header">
          <span><el-icon><EditPen /></el-icon> 待确认台账（本期 {{ draftRows.length }} 平台）—— 抖音可改佣金；付款金额/回款为本期共享</span>
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
          <template #default="{ row }"><el-input-number v-model="row.room_nights" :min="0" :precision="0" size="small" controls-position="right" style="width:78px" @change="onDraftResetJinying(row)" /></template>
        </el-table-column>
        <el-table-column label="服务商到账" width="130" align="right">
          <template #default="{ row }">{{ fmtMoney(row.base_received) }}</template>
        </el-table-column>
        <el-table-column label="服务商佣金" width="140" align="right">
          <template #default="{ row }">
            <el-input-number v-if="row.platform === '抖音'" v-model="row.supplier_commission" :min="0" :precision="2" :step="100" size="small" controls-position="right" style="width:120px" @change="onDraftResetJinying(row)" />
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="景区核销金额" width="130" align="right">
          <template #default="{ row }"><span class="calc">{{ fmtMoney(rowHexiao(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="景区待核销金额" width="140" align="right">
          <template #default="{ row }"><span class="calc pending">{{ fmtMoney(draftPending(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="付款金额（本期共享）" width="150" align="right">
          <template #default="{ row }"><el-input-number v-model="row.payment_amount" :min="0" :precision="2" :step="1000" size="small" controls-position="right" style="width:120px" @change="syncPayment(row.payment_amount)" /></template>
        </el-table-column>
        <el-table-column label="结算金额（可改）" width="160" align="right">
          <template #default="{ row }"><el-input-number v-model="row.jinying_amount" :min="0" :precision="2" :step="1000" size="small" controls-position="right" style="width:140px" @change="row.jinyingEdited = true" /></template>
        </el-table-column>
        <el-table-column label="服务费" width="110" align="right">
          <template #default="{ row }"><span class="calc">{{ fmtMoney(rowFeeDisplay(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="回款日期（本期共享）" width="160">
          <template #default="{ row }"><el-date-picker v-model="row.repay_date" type="date" value-format="YYYY-MM-DD" size="small" placeholder="手工" style="width:130px" @change="syncRepayDate(row.repay_date)" /></template>
        </el-table-column>
        <el-table-column label="回款金额（本期共享）" width="150" align="right">
          <template #default="{ row }"><el-input-number v-model="row.repay_amount" :min="0" :precision="2" :step="1000" size="small" controls-position="right" style="width:120px" @change="syncRepayAmount(row.repay_amount)" /></template>
        </el-table-column>
      </el-table>
      <div class="draft-note">提示：付款金额/回款为「本期各平台共享」，任填一行自动同步全平台；付款金额台账中隐藏、数据库留存，参与「景区待核销」整期递推。</div>
    </el-card>

    <!-- 已保存台账（按核对日期升序，隐藏付款金额，含本期合计行） -->
    <el-table :data="displayRows" border stripe size="small" class="saved-table" :row-class-name="rowClass">
      <el-table-column label="景区ID" width="150" fixed="left">
        <template #default="{ row }">{{ row.isTotal ? '' : scenicName }}</template>
      </el-table-column>
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
        <!-- 整期滚动余额：仅在「本期合计」行显示，平台行留空 -->
        <template #default="{ row }"><span v-if="row.isTotal" class="pending">{{ fmtMoney(row.pending_writeoff) }}</span></template>
      </el-table-column>
      <el-table-column label="结算金额" width="130" align="right">
        <template #default="{ row }">{{ fmtMoney(row.jinying_amount) }}</template>
      </el-table-column>
      <el-table-column label="服务费" width="110" align="right">
        <template #default="{ row }">{{ fmtMoney(row.service_fee) }}</template>
      </el-table-column>
      <!-- 间夜列已隐藏（数据库仍保存 room_nights 字段，参与服务费计算与编辑） -->
      <el-table-column label="回款日期" width="110">
        <!-- 回款每期共享：仅在「本期合计」行显示，平台行留空 -->
        <template #default="{ row }">{{ row.isTotal ? (row.repay_date || '') : '' }}</template>
      </el-table-column>
      <el-table-column label="回款金额" width="130" align="right">
        <template #default="{ row }">{{ row.isTotal ? (row.repay_amount != null ? fmtMoney(row.repay_amount) : '—') : '' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <template v-if="!row.isTotal && canEdit">
            <el-button size="small" text type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" text type="danger" @click="onDeleteRow(row)">删除</el-button>
          </template>
        </template>
      </el-table-column>
      <!-- 状态：仅本期合计行有内容；确认函上传/查看/下载/删除仅业务复核+信息维护 -->
      <el-table-column label="状态" width="250" fixed="right">
        <template #default="{ row }">
          <template v-if="row.isTotal">
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

    <!-- 编辑单行弹窗 -->
    <el-dialog v-model="editVisible" title="编辑台账行" width="480px">
      <el-form label-width="130px" v-if="editRow">
        <el-form-item label="平台">
          <el-input :model-value="editRow.platform" disabled style="width:100%" />
        </el-form-item>
        <el-form-item label="酒店名称">
          <el-input v-model="editForm.hotel_name" style="width:100%" />
        </el-form-item>
        <el-form-item label="服务费算法">
          <el-radio-group v-model="editForm.fee_algo">
            <el-radio :value="1">算法1（间夜×每间夜服务费）</el-radio>
            <el-radio :value="2">算法2（结算基数×结算费率）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="服务商到账">
          <el-input :model-value="fmtMoney(editRow.base_received)" disabled style="width:100%" />
        </el-form-item>
        <el-form-item v-if="editRow.platform === '抖音'" label="服务商佣金">
          <el-input-number v-model="editForm.supplier_commission" :min="0" :precision="2" :step="100" controls-position="right" style="width:100%" />
        </el-form-item>
        <el-form-item label="核销率">
          <el-input-number v-model="editForm.ratePctHexiao" :min="0" :max="100" :precision="2" :step="1" controls-position="right" style="width:100%" /><span class="pct-suffix">%</span>
        </el-form-item>
        <el-form-item v-if="editForm.fee_algo === 1" label="间夜">
          <el-input-number v-model="editForm.room_nights" :min="0" :precision="0" controls-position="right" style="width:100%" />
        </el-form-item>
        <el-form-item v-if="editForm.fee_algo === 1" label="每间夜服务费">
          <el-input-number v-model="editForm.fee_per_night" :min="0" :precision="2" :step="1" controls-position="right" style="width:100%" /><span class="pct-suffix">元</span>
        </el-form-item>
        <el-form-item v-if="editForm.fee_algo === 2" label="结算费率">
          <el-input-number v-model="editForm.ratePctSettle" :min="0" :max="100" :precision="2" :step="1" controls-position="right" style="width:100%" /><span class="pct-suffix">%</span>
        </el-form-item>
        <el-form-item label="结算金额">
          <el-input-number v-model="editForm.jinying_amount" :min="0" :precision="2" :step="1000" controls-position="right" style="width:100%" @change="editForm.jinyingEdited = true" />
          <div class="edit-hint">{{ editForm.fee_algo === 2 ? '默认 = 结算基数 × 结算费率' : '默认 = 景区核销 + 服务费（间夜 × 每间夜服务费）' }}（改佣金/费率/算法自动跟随、逐日累加）；可手工改，服务费 = 结算 − 核销</div>
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
import { ref, computed, watch, reactive, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Refresh, Download, House, EditPen, Check } from '@element-plus/icons-vue'
import {
  parseHotelFile, getHotelLedger, saveHotelLedger,
  updateHotelRow, deleteHotelRow, fetchHotelLedgerExportBlob,
  uploadHotelConfirm, deleteHotelConfirm, fetchHotelConfirmBlob
} from '@/api/hotelLedger'
import { downloadBlob } from '@/utils/file'
import { getScenicById } from '@/constants/scenic'
import { ROLES } from '@/constants/business'
import { useUserStore } from '@/store/user'

const props = defineProps({ scenicId: { type: String, required: true } })

const userStore = useUserStore()
// 景区ID = 景区名（与客户档案「客户ID」内容一致，作为关联键）
const scenicName = computed(() => getScenicById(props.scenicId)?.name || props.scenicId)
// 上传/编辑/删除台账：业务经办 + 信息维护(超管)
const canEdit = computed(() => userStore.isSuperuser || userStore.role === ROLES.BUSINESS_HANDLER)
// 确认函上传/查看/下载/删除：业务复核 + 信息维护(超管)
const canConfirm = computed(() => userStore.isSuperuser || userStore.role === ROLES.BUSINESS_REVIEWER)

const DEFAULT_RATE_HEXIAO = 0.9
const DEFAULT_FEE_PER_NIGHT = 44
const DEFAULT_RATE_SETTLE = 0.94   // 算法2 结算费率默认（结算金额=结算基数×结算费率）
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
// 改佣金/间夜 → 结算金额回到默认(算法1: 核销+间夜×费, JS 预览)并清手工标记
function onDraftResetJinying(row) {
  row.jinying_amount = calcJinying(row)
  row.jinyingEdited = false
}
// 服务费 = 结算金额 − 景区核销金额（结算金额可手工改）
function rowFeeDisplay(row) { return round2((Number(row.jinying_amount) || 0) - rowHexiao(row)) }

// 上一期末待核销（整期滚动起点）：savedRows 按 period_start 升序 → 末行所属期的 pending（同期同值）
const lastPeriodPending = computed(() => {
  const rows = savedRows.value
  return rows.length ? (Number(rows[rows.length - 1].pending_writeoff) || 0) : 0
})
// 本期（草稿）整期滚动待核销 = 上期待核销 + 本期共享付款 − 本期各平台核销合计（每行显示同一值）
const draftPeriodPending = computed(() => {
  const pay = Number(draftRows.value[0]?.payment_amount) || 0
  const hexiaoSum = draftRows.value.reduce((a, r) => a + rowHexiao(r), 0)
  return round2(lastPeriodPending.value + pay - hexiaoSum)
})
function draftPending() { return draftPeriodPending.value }
// 付款金额/回款日期/回款金额 每期各平台共享：任一行修改即同步到本期所有平台行
function syncPayment(val) { draftRows.value.forEach((r) => { r.payment_amount = val }) }
function syncRepayDate(val) { draftRows.value.forEach((r) => { r.repay_date = val }) }
function syncRepayAmount(val) { draftRows.value.forEach((r) => { r.repay_amount = val }) }

function fmtMoney(n) {
  const v = Number(n)
  if (Number.isNaN(v)) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const periodCount = computed(() => new Set(savedRows.value.map((r) => r.source_file || r.detail_name || r.check_date_text)).size)

// 平台展示顺序
const PLAT_ORDER = { '抖音': 0, '美团': 1, '携程': 2 }
// 期合计行的核对日期文案：取本期内各平台的最早起~最晚止
function periodSpan(rows) {
  const starts = rows.map((r) => r.period_start).filter(Boolean).sort()
  const ends = rows.map((r) => r.period_end).filter(Boolean).sort()
  const fmt = (d) => (d ? String(d).slice(0, 10) : '')
  if (!starts.length && !ends.length) return rows[0]?.check_date_text || ''
  return `${fmt(starts[0])} ~ ${fmt(ends[ends.length - 1])}`
}
// 展示行：**按「一份对账明细=一期」分组**（同一 source_file 为一期，含其全部平台行 + 1 本期合计行）；
// 期按核对日期(最早起)升序。修复：此前按各平台不同的核对日期分组导致同一期被拆散。
const displayRows = computed(() => {
  const groups = new Map()
  for (const r of savedRows.value) {
    const key = r.source_file || r.detail_name || r.check_date_text || r.period_text || '未分组'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(r)
  }
  // 每期排序键 = 期内最早 period_start
  const buckets = [...groups.values()].map((rows) => {
    const rowsSorted = [...rows].sort((a, b) => (PLAT_ORDER[a.platform] ?? 9) - (PLAT_ORDER[b.platform] ?? 9))
    const minStart = rows.map((r) => r.period_start).filter(Boolean).sort()[0] || ''
    return { rows: rowsSorted, minStart }
  })
  buckets.sort((a, b) => String(a.minStart).localeCompare(String(b.minStart)))

  const out = []
  for (const b of buckets) {
    const t = {
      isTotal: true, platform: '本期合计', check_date_text: periodSpan(b.rows),
      hexiao_amount: 0, pending_writeoff: 0, jinying_amount: 0, service_fee: 0, room_nights: 0,
      repay_date: '', repay_amount: null
    }
    for (const r of b.rows) {
      t.hexiao_amount += Number(r.hexiao_amount) || 0
      t.jinying_amount += Number(r.jinying_amount) || 0
      t.service_fee += Number(r.service_fee) || 0
      t.room_nights += Number(r.room_nights) || 0
    }
    // 待核销为整期滚动余额（同期各行同值）→ 取一次；回款每期共享 → 取代表值，均不累加
    t.pending_writeoff = Number(b.rows[0]?.pending_writeoff) || 0
    const rep = b.rows.find((r) => r.repay_amount != null)
    t.repay_amount = rep ? Number(rep.repay_amount) : null
    t.repay_date = (b.rows.find((r) => r.repay_date) || {}).repay_date || ''
    // 本期确认函（同期共享）：任一行 id 作操作句柄
    t.period_row_id = b.rows[0]?.id
    t.confirm_stored = b.rows[0]?.confirm_stored || ''
    t.confirm_name = b.rows[0]?.confirm_name || ''
    out.push(...b.rows, t)
  }
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
      // 逐日明细透传持久化（编辑改费率/佣金/算法时后端按天重算）
      daily_json: p.daily_json || '',
      // 结算金额默认=逐日累加值，可手工改；jinyingEdited 标记是否被手工改过
      jinying_amount: Number(p.def_jinying) || 0,
      jinyingEdited: false,
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
    daily_json: r.daily_json,
    // 结算金额仅在手工改过时上传(覆盖)，否则由后端逐日累加
    jinying_amount: r.jinyingEdited ? r.jinying_amount : null,
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
  ratePctHexiao: 90, fee_algo: 1, fee_per_night: 44, ratePctSettle: 94,
  jinying_amount: 0, jinyingEdited: false, payment_amount: 0, repay_date: null, repay_amount: null
})
// 编辑弹窗：结算基数/核销/结算金额（派生只读预览；保存后由后端按逐日累加得精确值）
const editSettleBase = computed(() => {
  if (!editRow.value) return 0
  const comm = editRow.value.platform === '抖音' ? (Number(editForm.supplier_commission) || 0) : 0
  return round2((Number(editRow.value.base_received) || 0) - comm)
})
const editHexiao = computed(() => round2(editSettleBase.value * (Number(editForm.ratePctHexiao) || 0) / 100))
const editJinying = computed(() => {
  if (Number(editForm.fee_algo) === 2) {
    return round2(editSettleBase.value * (Number(editForm.ratePctSettle) || 0) / 100)
  }
  const fee = round2((Number(editForm.room_nights) || 0) * (Number(editForm.fee_per_night) || 0))
  return round2(editHexiao.value + fee)
})
// 改佣金/核销率/算法/间夜/结算费率 → 结算金额回到默认(跟随)并清手工标记；openEdit 期间抑制
let suppressJinyingWatch = false
watch(
  () => [editForm.supplier_commission, editForm.ratePctHexiao, editForm.fee_algo,
    editForm.fee_per_night, editForm.room_nights, editForm.ratePctSettle],
  () => {
    if (suppressJinyingWatch) return
    editForm.jinying_amount = editJinying.value
    editForm.jinyingEdited = false
  }
)
function openEdit(row) {
  suppressJinyingWatch = true   // 载入既有值期间不触发跟随
  editRow.value = row
  editForm.hotel_name = row.hotel_name
  editForm.supplier_commission = Number(row.supplier_commission) || 0
  editForm.room_nights = Number(row.room_nights) || 0
  editForm.ratePctHexiao = round2((Number(row.rate_hexiao) || DEFAULT_RATE_HEXIAO) * 100)
  editForm.fee_algo = Number(row.fee_algo) || 1
  editForm.fee_per_night = Number(row.fee_per_night) || DEFAULT_FEE_PER_NIGHT
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
      hotel_name: editForm.hotel_name,
      supplier_commission: editForm.supplier_commission,
      room_nights: editForm.room_nights,
      rate_hexiao: round2(Number(editForm.ratePctHexiao) / 100),
      fee_algo: editForm.fee_algo,
      fee_per_night: editForm.fee_per_night,
      rate_settle: round2(Number(editForm.ratePctSettle) / 100),
      payment_amount: editForm.payment_amount,
      repay_date: editForm.repay_date,
      repay_amount: editForm.repay_amount
    }
    // 仅当手工改过结算金额才上传覆盖，否则由后端逐日累加
    if (editForm.jinyingEdited) payload.jinying_amount = editForm.jinying_amount
    await updateHotelRow(props.scenicId, editRow.value.id, payload)
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

// —— 本期确认函（业务复核/信息维护）——
async function onConfirmPick(row, file) {
  const raw = file?.raw
  if (!raw) return
  try {
    await uploadHotelConfirm(props.scenicId, row.period_row_id, raw)
    ElMessage.success('确认函已上传，本期状态：已确认')
    await loadSaved()
  } catch {
    ElMessage.error('确认函上传失败')
  }
}
async function onConfirmView(row) {
  try {
    const blob = await fetchHotelConfirmBlob(props.scenicId, row.confirm_stored, row.confirm_name)
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch {
    ElMessage.error('查看失败')
  }
}
async function onConfirmDownload(row) {
  try {
    const blob = await fetchHotelConfirmBlob(props.scenicId, row.confirm_stored, row.confirm_name)
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
    await deleteHotelConfirm(props.scenicId, row.period_row_id)
    ElMessage.success('确认函已删除，本期状态：未确认')
    await loadSaved()
  } catch {
    ElMessage.error('删除失败')
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
