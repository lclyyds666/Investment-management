<template>
  <div class="ds" :class="fullscreen ? 'ds-full' : 'ds-embed'">
    <!-- 顶部标题栏 -->
    <header class="screen-head">
      <div class="head-side left">
        <span class="dot online"></span> 系统在线
        <span class="sep">|</span> 身份：{{ userStore.roleLabel || '—' }}
      </div>
      <h1 class="head-title">
        <span class="title-cn">山东出版供应链管理 · 数据指挥中心</span>
        <span class="title-en">SD PUBLISHING SUPPLY-CHAIN DATA CENTER</span>
      </h1>
      <div class="head-side right">
        <span class="clock">{{ clock }}</span>
        <span class="sep">|</span> {{ today }}
        <el-button class="scr-btn" size="small" round @click="toggleScreen">
          <el-icon><component :is="fullscreen ? 'Close' : 'FullScreen'" /></el-icon>
          <span>{{ fullscreen ? '退出' : '全屏投放' }}</span>
        </el-button>
      </div>
    </header>

    <div class="screen-body">
      <!-- 左侧：核心经营指标 + 面积图 -->
      <section class="col col-left">
        <div class="panel">
          <div class="panel-title">核心经营指标 <em>{{ regionLabel }}</em></div>
          <div class="metrics" :key="'m' + flipKey">
            <div class="metric" v-for="m in metricCards" :key="m.label">
              <div class="metric-ico">{{ m.ico }}</div>
              <div class="metric-body">
                <div class="metric-label">{{ m.label }}</div>
                <div class="metric-value" :style="{ color: m.color, textShadow: '0 0 12px ' + m.color }">
                  <CountTo :value="m.value" :prefix="m.prefix || ''" :suffix="m.suffix || ''" />
                </div>
              </div>
            </div>
          </div>
          <div v-if="mode === 'region'" class="back-national">
            <el-button size="small" text @click="resetNational">← 返回全国视图</el-button>
          </div>
        </div>

        <div class="panel grow">
          <div class="panel-title">营收月度趋势</div>
          <BaseChart :option="areaOption" :height="fullscreen ? '300px' : '240px'" />
        </div>
      </section>

      <!-- 中间：天眼地图 -->
      <section class="col col-center">
        <div class="panel panel-map grow">
          <div class="panel-title center">
            全国业务天眼 · 实时物流飞线 <em>点击省份 · 两侧数据联动</em>
          </div>
          <ScreenMap hub="山东省" :height="fullscreen ? '660px' : '600px'" @province-click="onProvince" />
        </div>
      </section>

      <!-- 右侧：审批跑马灯(可选) + AI 分析舱 -->
      <section class="col col-right">
        <div v-if="showApproval" class="panel">
          <div class="panel-title">7 级审批流 · 实时动态</div>
          <div class="marquee" @mouseenter="pauseMarquee = true" @mouseleave="pauseMarquee = false">
            <div class="marquee-track" :class="{ paused: pauseMarquee }">
              <div class="mq-item" v-for="(it, i) in marqueeLoop" :key="i">
                <span class="mq-no">{{ it.no }}</span>
                <span class="mq-title">{{ it.title }}</span>
                <span class="mq-role">{{ it.role }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="panel grow" :key="'ai' + flipKey">
          <div class="panel-title">AI 智能大脑 · 风险雷达</div>
          <BaseChart :option="radarOption" :height="fullscreen ? '280px' : '230px'" />
          <div class="ai-typer">
            <span class="ai-tag">AI</span>
            <span class="ai-text">{{ typed }}<span class="caret">▋</span></span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import BaseChart from '@/components/BaseChart.vue'
import CountTo from '@/components/screen/CountTo.vue'
import ScreenMap from '@/components/screen/ScreenMap.vue'
import { getDashboard, aiDiagnose, getFinancial } from '@/api/operation'
import { listContracts } from '@/api/contract'
import { chartVisualTokens as visual } from '@/utils/visualTokens'

const props = defineProps({
  fullscreen: { type: Boolean, default: false },
  // 是否显示「合同审批动态」跑马灯（战略总览页关闭，大屏投放保留）
  showApproval: { type: Boolean, default: true }
})
const router = useRouter()
const userStore = useUserStore()

function toggleScreen() {
  if (props.fullscreen) {
    if (document.fullscreenElement) document.exitFullscreen?.()
    router.push('/')
  } else {
    router.push('/screen')
  }
}

/* 时钟 */
const clock = ref('')
const today = ref('')
let clockTimer = null
function tickClock() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  clock.value = `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
  today.value = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/* 数据 */
const dash = ref({ kpi: {}, trend: [] })
const fin = ref(null)
const pendingCount = ref(0)
const ai = ref(null)
const provinceData = [
  { name: '山东省', value: 4200000 }, { name: '广东省', value: 3800000 },
  { name: '江苏省', value: 3100000 }, { name: '浙江省', value: 2900000 },
  { name: '北京市', value: 2600000 }, { name: '上海市', value: 2400000 },
  { name: '湖北省', value: 1500000 }, { name: '河南省', value: 1800000 },
  { name: '四川省', value: 1600000 }, { name: '河北省', value: 1400000 },
  { name: '福建省', value: 1300000 }, { name: '辽宁省', value: 1100000 }
]

/* 省份联动 */
const mode = ref('national')
const region = ref('')
const flipKey = ref(0)
const regionLabel = computed(() => (mode.value === 'region' ? region.value : '全国'))
function onProvince(name) { region.value = name; mode.value = 'region'; flipKey.value++ }
function resetNational() { mode.value = 'national'; flipKey.value++ }

const metricCards = computed(() => {
  // 省份下钻视图：沿用地图联动的示意数据
  if (mode.value === 'region') {
    const p = provinceData.find((d) => d.name === region.value)
    const v = p ? p.value : 800000
    return [
      { label: '区域营收(元)', value: v, color: visual.screenSecondary, ico: '💰', prefix: '¥' },
      { label: '区域利润(元)', value: Math.round(v * 0.3), color: visual.screenPrimary, ico: '📈', prefix: '¥' },
      { label: '订单总数', value: Math.round(v / 7250), color: visual.screenAccent, ico: '📦' },
      { label: '待审批合同', value: pendingCount.value, color: visual.screenDanger, ico: '📝' }
    ]
  }
  // 全国视图：展示文旅门票/酒店台账指标（与经营页同源，实时同步）
  const f = fin.value || {}
  return [
    { label: '已投入业务规模', value: Number(f.existing_scale || 0), color: visual.screenAccent, ico: '💼', prefix: '¥' },
    { label: '已实现业务规模', value: Number(f.total_realized_scale || 0), color: visual.screenSecondary, ico: '📊', prefix: '¥' },
    { label: '已实现业务毛利润', value: Number(f.total_gross_income || 0), color: visual.screenPrimary, ico: '💰', prefix: '¥' },
    { label: '待审批合同', value: pendingCount.value, color: visual.screenDanger, ico: '📝' }
  ]
})

const areaOption = computed(() => {
  const t = dash.value.trend || []
  const months = t.map((x) => x.month.slice(5) + '月')
  const revenue = t.map((x) => Number(x.revenue))
  return {
    backgroundColor: 'transparent',
    grid: { left: 46, right: 16, top: 16, bottom: 24 },
    tooltip: { trigger: 'axis', backgroundColor: visual.screenTooltip, borderColor: visual.screenPrimary, textStyle: { color: visual.screenText } },
    xAxis: { type: 'category', data: months, axisLabel: { color: visual.screenTextMuted }, axisLine: { lineStyle: { color: visual.screenAxis } } },
    yAxis: { type: 'value', axisLabel: { color: visual.screenTextMuted, formatter: (v) => v / 10000 + '万' }, splitLine: { lineStyle: { color: visual.screenAxis } } },
    series: [{
      type: 'line', smooth: true, symbol: 'none', data: revenue,
      lineStyle: { color: visual.screenSecondary, width: 2, shadowBlur: 10, shadowColor: visual.screenSecondary },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [
        { offset: 0, color: visual.screenSecondaryGlow }, { offset: 1, color: visual.screenSecondaryFade }
      ] } }
    }]
  }
})

/* 审批跑马灯：实时读取数据库中处于审批中的真实合同 */
const pauseMarquee = ref(false)
const marquee = ref([])
const marqueeLoop = computed(() => {
  const base = marquee.value.length
    ? marquee.value
    : [{ no: '—', title: '当前暂无审批中的合同', role: '待提交' }]
  return [...base, ...base] // 复制一份用于无缝滚动
})

/* AI 雷达 + 打字机 */
const radarOption = computed(() => {
  const m = ai.value?.metrics || {}
  const margin = Number(m.margin || 0)
  const risks = ai.value?.risks?.length || 0
  const pInv = Number(m.pending_invoice || 0)
  const rev = Number(m.revenue || 1)
  const scores = [
    88, Math.max(40, 100 - risks * 12), Math.min(100, Math.round(margin * 3)),
    Math.max(50, 100 - (m.pending_contracts || 0) * 8),
    Math.max(40, Math.round(100 - (pInv / rev) * 100)), 92
  ]
  return {
    backgroundColor: 'transparent',
    radar: {
      radius: '65%',
      indicator: [
        { name: '资金合规', max: 100 }, { name: '风险防控', max: 100 }, { name: '盈利能力', max: 100 },
        { name: '审批时效', max: 100 }, { name: '回款健康', max: 100 }, { name: '数据质量', max: 100 }
      ],
      axisName: { color: visual.screenText, fontSize: 11 },
      splitLine: { lineStyle: { color: visual.screenPrimarySoft } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: visual.screenPrimarySoft } }
    },
    series: [{
      type: 'radar',
      data: [{ value: scores, areaStyle: { color: visual.screenSecondarySoft }, lineStyle: { color: visual.screenSecondary, width: 2 }, itemStyle: { color: visual.screenSecondary } }]
    }]
  }
})
const aiMessages = computed(() => {
  if (!ai.value) return ['AI 智能大脑待命中…']
  const rs = (ai.value.risks || []).map((r) => `【${r.level}风险】${r.title}：${r.detail}`)
  const ss = (ai.value.suggestions || []).map((s) => `【资金建议】${s.title}：${s.detail}`)
  return [ai.value.summary, ...rs, ...ss]
})
const typed = ref('')
let typerTimer = null
function startTyper() {
  stopTyper()
  let mi = 0
  const typeMsg = () => {
    const msgs = aiMessages.value
    if (!msgs.length) { typerTimer = setTimeout(typeMsg, 500); return }
    const cur = String(msgs[mi % msgs.length] || '')
    let ci = 0; typed.value = ''
    const step = () => {
      ci++; typed.value = cur.slice(0, ci)
      if (ci < cur.length) typerTimer = setTimeout(step, 36)
      else typerTimer = setTimeout(() => { mi++; typeMsg() }, 2400)
    }
    step()
  }
  typeMsg()
}
function stopTyper() { if (typerTimer) { clearTimeout(typerTimer); typerTimer = null } }

/* 实时数据加载（大屏常驻，定时轮询保持与数据库同步） */
async function loadDashboard() {
  try { dash.value = await getDashboard(2026) } catch (e) { /* ignore */ }
}
async function loadFinancial() {
  try { fin.value = await getFinancial() } catch (e) { /* ignore */ }
}
async function loadContracts() {
  try {
    const list = await listContracts()
    const pending = list.filter((c) => c.status === 'pending')
    pendingCount.value = pending.length
    marquee.value = pending.map((c) => ({
      no: c.contract_no, title: c.title, role: c.current_role_label || '审批中'
    }))
  } catch (e) { /* ignore */ }
}

let pollTimer = null
onMounted(async () => {
  tickClock(); clockTimer = setInterval(tickClock, 1000)
  await loadDashboard()
  await loadFinancial()
  await loadContracts()
  try { ai.value = await aiDiagnose(2026) } catch (e) { /* ignore */ }
  startTyper()
  // 经营/财务数据与审批流每 20s 轮询刷新（AI 诊断成本较高，仅首屏加载一次）
  pollTimer = setInterval(() => { loadDashboard(); loadFinancial(); loadContracts() }, 20000)
})
onBeforeUnmount(() => { clearInterval(clockTimer); clearInterval(pollTimer); stopTyper() })
</script>

<style scoped lang="scss">
.ds {
  background:
    radial-gradient(1200px 600px at 50% -10%, color-mix(in srgb, var(--screen-primary) 16%, transparent), transparent 60%),
    radial-gradient(900px 500px at 90% 110%, color-mix(in srgb, var(--screen-secondary) 11%, transparent), transparent 60%),
    var(--screen-bg);
  color: var(--screen-text);
  font-family: var(--font-body);
  box-sizing: border-box;
}
.ds-embed { margin: -20px; padding: 14px 18px 18px; min-height: calc(100vh - 60px); }
.ds-full { margin: 0; padding: 14px 20px; min-height: 100vh; }

.screen-head { display: grid; grid-template-columns: minmax(220px, 1fr) minmax(380px, 1.4fr) minmax(220px, 1fr); align-items: center; padding: 6px 8px 14px; border-bottom: 1px solid var(--screen-border); }
.head-title { margin: 0; text-align: center; line-height: 1.2; flex: 1; }
.title-cn { display: block; font-size: clamp(20px, 1.65vw, 26px); font-family: var(--font-display); font-weight: 800; letter-spacing: 3px; color: var(--screen-text); }
.title-en { display: block; font-size: 10px; letter-spacing: 4px; color: var(--screen-text-muted); margin-top: 5px; }
.head-side { min-width: 0; display: flex; align-items: center; color: var(--screen-text-muted); font-size: 12px; }
.head-side.right { justify-content: flex-end; gap: 4px; }
.head-side.left { gap: 2px; }
.clock { color: var(--screen-secondary); font-family: var(--font-data); font-weight: 700; font-size: 16px; letter-spacing: 1px; }
.sep { margin: 0 8px; color: var(--screen-border); }
.scr-btn { margin-left: 10px; background: var(--screen-surface); border-color: var(--screen-border); color: var(--screen-text); }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; }
.dot.online { background: var(--screen-secondary); box-shadow: 0 0 8px var(--screen-secondary); animation: pulse 1.6s infinite; }
@keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: .35 } }

.screen-body { display: grid; grid-template-columns: minmax(260px, .82fr) minmax(470px, 1.45fr) minmax(260px, .82fr); gap: 16px; margin-top: 14px; }
.col { display: flex; flex-direction: column; gap: 16px; }
.col-left, .col-right { min-width: 0; }
.col-center { min-width: 0; }
.grow { flex: 1; }

.panel { position: relative; min-width: 0; background: var(--screen-surface); backdrop-filter: blur(12px); border: 1px solid var(--screen-border); border-radius: var(--radius-md); padding: 14px 16px; box-shadow: var(--screen-shadow); }
.panel-map { padding: 8px 10px; }
.panel-title { font-size: 14px; font-weight: 750; color: var(--screen-text); margin-bottom: 12px; padding-left: 10px; border-left: 3px solid var(--screen-secondary); letter-spacing: 1px; display: flex; align-items: baseline; gap: 8px; em { font-style: normal; font-size: 11px; color: var(--screen-text-muted); } &.center { justify-content: center; border-left: none; padding-left: 0; } }

.metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; animation: flipIn .6s ease; }
@keyframes flipIn { from { transform: rotateX(90deg); opacity: 0 } to { transform: rotateX(0); opacity: 1 } }
.metric { min-width: 0; display: flex; align-items: center; gap: 10px; background: var(--screen-surface-strong); border: 1px solid var(--screen-border); border-radius: var(--radius-sm); padding: 12px; transition: all var(--motion-base) ease; }
.metric:hover { border-color: var(--screen-primary); transform: translateY(-2px); }
.metric-ico { font-size: 24px; }
.metric-label { font-size: 11px; color: var(--screen-text-muted); }
.metric-value { font-size: clamp(18px, 1.45vw, 24px); font-weight: 800; margin-top: 5px; overflow-wrap: anywhere; }
.back-national { margin-top: 10px; text-align: right; :deep(.el-button) { color: var(--screen-text-muted); } }

.marquee { height: 168px; overflow: hidden; position: relative; }
.marquee-track { display: flex; flex-direction: column; animation: scrollUp 16s linear infinite; }
.marquee-track.paused { animation-play-state: paused; }
@keyframes scrollUp { from { transform: translateY(0) } to { transform: translateY(-50%) } }
.mq-item { display: flex; align-items: center; gap: 8px; padding: 9px 10px; margin-bottom: 8px; background: var(--screen-surface-strong); border-left: 2px solid var(--screen-primary); border-radius: var(--radius-xs); font-size: 12px; }
.mq-no { color: var(--screen-secondary); font-family: var(--font-data); flex: 0 0 auto; }
.mq-title { flex: 1; color: var(--screen-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mq-role { flex: 0 0 auto; color: var(--screen-accent); background: color-mix(in srgb, var(--screen-accent) 12%, transparent); padding: 2px 8px; border-radius: var(--el-border-radius-round); }

.ai-typer { margin-top: 10px; min-height: 66px; padding: 10px 12px; background: var(--screen-surface-strong); border: 1px solid var(--screen-border); border-radius: var(--radius-sm); font-size: 12.5px; line-height: 1.7; color: var(--screen-text); }
.ai-tag { display: inline-block; background: var(--screen-secondary); color: var(--screen-bg); font-weight: 800; border-radius: var(--radius-xs); padding: 0 6px; margin-right: 8px; font-size: 11px; }
.caret { color: var(--screen-secondary); animation: blink 1s steps(1) infinite; }
@keyframes blink { 50% { opacity: 0 } }

@media (max-width: 1180px) {
  .screen-head { grid-template-columns: 1fr auto; }
  .head-title { grid-column: 1 / -1; grid-row: 1; margin-bottom: 10px; }
  .head-side { grid-row: 2; }
  .screen-body { grid-template-columns: 1fr; }
  .col-center { grid-row: 1; }
  .col-left, .col-right { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
