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
          <ScreenMap :data="provinceData" hub="山东省" :height="fullscreen ? '660px' : '600px'" @province-click="onProvince" />
        </div>
      </section>

      <!-- 右侧：审批跑马灯 + AI 分析舱 -->
      <section class="col col-right">
        <div class="panel">
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
import { getDashboard, aiDiagnose } from '@/api/operation'
import { listContracts } from '@/api/contract'

const props = defineProps({ fullscreen: { type: Boolean, default: false } })
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
  const k = dash.value.kpi || {}
  let revenue = Number(k.total_revenue || 0)
  let profit = Number(k.total_profit || 0)
  let orders = Number(k.total_orders || 0)
  if (mode.value === 'region') {
    const p = provinceData.find((d) => d.name === region.value)
    const v = p ? p.value : 800000
    revenue = v; profit = Math.round(v * 0.3); orders = Math.round(v / 7250)
  }
  return [
    { label: '总营收(元)', value: revenue, color: '#2de1c2', ico: '💰', prefix: '¥' },
    { label: '总利润(元)', value: profit, color: '#39c5ff', ico: '📈', prefix: '¥' },
    { label: '订单总数', value: orders, color: '#ffd34e', ico: '📦' },
    { label: '待审批合同', value: pendingCount.value, color: '#ff7ac6', ico: '📝' }
  ]
})

const areaOption = computed(() => {
  const t = dash.value.trend || []
  const months = t.map((x) => x.month.slice(5) + '月')
  const revenue = t.map((x) => Number(x.revenue))
  return {
    backgroundColor: 'transparent',
    grid: { left: 46, right: 16, top: 16, bottom: 24 },
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(4,20,48,0.9)', borderColor: '#1c9be6', textStyle: { color: '#cfe8ff' } },
    xAxis: { type: 'category', data: months, axisLabel: { color: '#7fa8d0' }, axisLine: { lineStyle: { color: '#1c3a66' } } },
    yAxis: { type: 'value', axisLabel: { color: '#7fa8d0', formatter: (v) => v / 10000 + '万' }, splitLine: { lineStyle: { color: 'rgba(28,58,102,0.4)' } } },
    series: [{
      type: 'line', smooth: true, symbol: 'none', data: revenue,
      lineStyle: { color: '#2de1c2', width: 2, shadowBlur: 10, shadowColor: '#2de1c2' },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1, colorStops: [
        { offset: 0, color: 'rgba(45,225,194,0.5)' }, { offset: 1, color: 'rgba(45,225,194,0.02)' }
      ] } }
    }]
  }
})

/* 审批跑马灯 */
const pauseMarquee = ref(false)
const mockFlow = [
  { no: 'HT-2026-002', title: '数字出版平台技术服务合同', role: '业务复核' },
  { no: 'HT-2026-014', title: '2026秋季教材物流配送', role: '风控审核' },
  { no: 'HT-2026-018', title: '景区文创产品采购', role: '财务经办' },
  { no: 'HT-2026-021', title: '酒店渠道数据服务', role: '财务复核' },
  { no: 'HT-2026-025', title: '仓储智能化改造项目', role: '供管公司负责人' },
  { no: 'HT-2026-030', title: '数字阅读平台合作', role: '投资公司负责人' }
]
const marquee = ref([...mockFlow])
const marqueeLoop = computed(() => [...marquee.value, ...marquee.value])

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
      axisName: { color: '#9fd0ff', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(28,155,230,0.25)' } },
      splitArea: { show: false },
      axisLine: { lineStyle: { color: 'rgba(28,155,230,0.25)' } }
    },
    series: [{
      type: 'radar',
      data: [{ value: scores, areaStyle: { color: 'rgba(45,225,194,0.28)' }, lineStyle: { color: '#2de1c2', width: 2 }, itemStyle: { color: '#2de1c2' } }]
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

onMounted(async () => {
  tickClock(); clockTimer = setInterval(tickClock, 1000)
  try { dash.value = await getDashboard(2026) } catch (e) { /* ignore */ }
  try {
    const list = await listContracts()
    pendingCount.value = list.filter((c) => c.status === 'pending').length
    const real = list.filter((c) => c.status === 'pending')
      .map((c) => ({ no: c.contract_no, title: c.title, role: c.current_role_label || '审批中' }))
    marquee.value = [...real, ...mockFlow]
  } catch (e) { /* ignore */ }
  try { ai.value = await aiDiagnose(2026) } catch (e) { /* ignore */ }
  startTyper()
})
onBeforeUnmount(() => { clearInterval(clockTimer); stopTyper() })
</script>

<style scoped lang="scss">
.ds {
  background:
    radial-gradient(1200px 600px at 50% -10%, rgba(28,155,230,0.18), transparent 60%),
    radial-gradient(900px 500px at 90% 110%, rgba(45,225,194,0.12), transparent 60%),
    #000a1f;
  color: #cfe6ff;
  font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
  box-sizing: border-box;
}
.ds-embed { margin: -20px; padding: 14px 18px 18px; min-height: calc(100vh - 60px); }
.ds-full { margin: 0; padding: 14px 20px; min-height: 100vh; }

.screen-head { display: flex; align-items: center; justify-content: space-between; padding: 6px 8px 14px; border-bottom: 1px solid rgba(45,225,194,0.2); }
.head-title { margin: 0; text-align: center; line-height: 1.2; flex: 1; }
.title-cn { display: block; font-size: 24px; font-weight: 800; letter-spacing: 3px; background: linear-gradient(90deg, #39c5ff, #2de1c2); -webkit-background-clip: text; background-clip: text; color: transparent; text-shadow: 0 0 24px rgba(45,225,194,0.4); }
.title-en { display: block; font-size: 11px; letter-spacing: 4px; color: #4f7bb0; margin-top: 3px; }
.head-side { font-size: 13px; color: #7fa8d0; min-width: 300px; display: flex; align-items: center; }
.head-side.right { justify-content: flex-end; gap: 4px; }
.head-side.left { gap: 2px; }
.clock { color: #2de1c2; font-weight: 700; font-size: 16px; letter-spacing: 1px; }
.sep { margin: 0 8px; color: #26456f; }
.scr-btn { margin-left: 10px; background: rgba(28,155,230,0.15); border-color: rgba(45,225,194,0.5); color: #9fe9ff; }
.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px; }
.dot.online { background: #2de1c2; box-shadow: 0 0 8px #2de1c2; animation: pulse 1.6s infinite; }
@keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: .35 } }

.screen-body { display: flex; gap: 16px; margin-top: 14px; }
.col { display: flex; flex-direction: column; gap: 16px; }
.col-left, .col-right { width: 26%; }
.col-center { flex: 1; }
.grow { flex: 1; }

.panel { position: relative; background: rgba(10,28,60,0.45); backdrop-filter: blur(8px); border: 1px solid rgba(45,225,194,0.28); border-radius: 10px; padding: 14px 16px; box-shadow: 0 0 18px rgba(28,155,230,0.18), inset 0 0 26px rgba(28,155,230,0.06); }
.panel-map { padding: 8px 10px; }
.panel-title { font-size: 15px; font-weight: 700; color: #eafcff; margin-bottom: 12px; padding-left: 10px; border-left: 3px solid #2de1c2; letter-spacing: 1px; display: flex; align-items: baseline; gap: 8px; em { font-style: normal; font-size: 12px; color: #4f7bb0; } &.center { justify-content: center; border-left: none; padding-left: 0; } }

.metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; animation: flipIn .6s ease; }
@keyframes flipIn { from { transform: rotateX(90deg); opacity: 0 } to { transform: rotateX(0); opacity: 1 } }
.metric { display: flex; align-items: center; gap: 10px; background: rgba(6,20,46,0.6); border: 1px solid rgba(28,155,230,0.2); border-radius: 8px; padding: 12px; }
.metric-ico { font-size: 24px; }
.metric-label { font-size: 12px; color: #7fa8d0; }
.metric-value { font-size: 22px; font-weight: 800; margin-top: 4px; font-variant-numeric: tabular-nums; }
.back-national { margin-top: 10px; text-align: right; :deep(.el-button) { color: #7fa8d0; } }

.marquee { height: 168px; overflow: hidden; position: relative; }
.marquee-track { display: flex; flex-direction: column; animation: scrollUp 16s linear infinite; }
.marquee-track.paused { animation-play-state: paused; }
@keyframes scrollUp { from { transform: translateY(0) } to { transform: translateY(-50%) } }
.mq-item { display: flex; align-items: center; gap: 8px; padding: 9px 10px; margin-bottom: 8px; background: rgba(6,20,46,0.6); border-left: 2px solid #39c5ff; border-radius: 6px; font-size: 12px; }
.mq-no { color: #2de1c2; font-family: monospace; flex: 0 0 auto; }
.mq-title { flex: 1; color: #cfe6ff; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mq-role { flex: 0 0 auto; color: #ffd34e; background: rgba(255,211,78,0.12); padding: 2px 8px; border-radius: 10px; }

.ai-typer { margin-top: 10px; min-height: 66px; padding: 10px 12px; background: rgba(6,20,46,0.6); border: 1px solid rgba(45,225,194,0.2); border-radius: 8px; font-size: 12.5px; line-height: 1.7; color: #bfe8ff; }
.ai-tag { display: inline-block; background: linear-gradient(90deg,#39c5ff,#2de1c2); color: #002; font-weight: 800; border-radius: 4px; padding: 0 6px; margin-right: 8px; font-size: 11px; }
.caret { color: #2de1c2; animation: blink 1s steps(1) infinite; }
@keyframes blink { 50% { opacity: 0 } }
</style>
