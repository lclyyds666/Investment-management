<template>
  <div class="ds" :class="fullscreen ? 'ds-full' : 'ds-embed'">
    <header class="screen-head">
      <div class="head-side left">
        <span class="dot online"></span> 系统在线
        <span class="sep">|</span> 身份：{{ userStore.roleLabel || '—' }}
      </div>
      <h1 class="head-title">
        <span class="title-cn">山东出版供应链管理有限公司 · 数据指挥中心</span>
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

    <main class="screen-body">
      <section class="map-stage">
        <div class="map-heading">
          <span class="heading-mark"></span>
          <div>
            <h2>全国业务天眼</h2>
            <p>NATIONAL SCENIC BUSINESS VISION</p>
          </div>
        </div>

        <ScreenMap
          height="100%"
          :province-data="provinceMetrics"
          :selected-province="mode === 'region' ? region : ''"
          @province-click="onProvince"
        />

        <aside class="metrics-dock" :key="`metrics-${flipKey}`">
          <div class="dock-head">
            <div>
              <span class="dock-eyebrow">核心经营指标</span>
              <strong>{{ regionLabel }}</strong>
            </div>
            <button
              v-if="mode === 'region'"
              type="button"
              class="reset-button"
              @click="resetNational"
            >
              返回全国
            </button>
          </div>

          <div class="metrics">
            <article v-for="metric in metricCards" :key="metric.label" class="metric">
              <span class="metric-code">{{ metric.code }}</span>
              <div class="metric-body">
                <div class="metric-label">{{ metric.label }}</div>
                <div class="metric-value" :style="{ color: metric.color }">
                  <CountTo :value="metric.value" :decimals="2" prefix="¥" />
                </div>
                <div class="metric-unit">人民币 · 元</div>
              </div>
            </article>
          </div>

          <p class="dock-note">
            {{ mode === 'region' ? '当前省份数据由所属景区门票与酒店台账实时汇总' : '全国数据与经营数据中心保持同源' }}
          </p>
        </aside>

        <div class="map-guide">
          <span class="guide-pulse"></span>
          点击省份查看区域营收与利润，拖动或滚轮可调整地图
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import CountTo from '@/components/screen/CountTo.vue'
import ScreenMap from '@/components/screen/ScreenMap.vue'
import { getFinancial } from '@/api/operation'
import { getScenicById, scenicSpots } from '@/constants/scenic'
import { chartVisualTokens as visual } from '@/utils/visualTokens'

const props = defineProps({
  fullscreen: { type: Boolean, default: false }
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

const clock = ref('')
const today = ref('')
let clockTimer = null
function tickClock() {
  const now = new Date()
  const pad = (value) => String(value).padStart(2, '0')
  clock.value = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`
  today.value = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const fin = ref({
  total_realized_scale: 0,
  total_gross_income: 0,
  ledger_profit: []
})
const mode = ref('national')
const region = ref('')
const flipKey = ref(0)

const provinceMetrics = computed(() => {
  const metrics = new Map()
  for (const scenic of scenicSpots) {
    if (!scenic.province) continue
    if (!metrics.has(scenic.province)) {
      metrics.set(scenic.province, {
        name: scenic.province,
        revenue: 0,
        profit: 0,
        scenicIds: new Set()
      })
    }
    metrics.get(scenic.province).scenicIds.add(scenic.id)
  }

  for (const point of fin.value.ledger_profit || []) {
    const scenic = getScenicById(point.scenic_id)
    if (!scenic?.province) continue
    const current = metrics.get(scenic.province)
    current.revenue += Number(point.realized_amount || 0)
    current.profit += Number(point.service_fee || 0)
  }

  return [...metrics.values()].map((item) => ({
    name: item.name,
    revenue: item.revenue,
    profit: item.profit,
    scenicCount: item.scenicIds.size
  }))
})

const selectedProvince = computed(() => (
  provinceMetrics.value.find((item) => item.name === region.value)
  || { revenue: 0, profit: 0 }
))
const regionLabel = computed(() => (mode.value === 'region' ? region.value : '全国'))

function onProvince(name) {
  region.value = name
  mode.value = 'region'
  flipKey.value += 1
}

function resetNational() {
  region.value = ''
  mode.value = 'national'
  flipKey.value += 1
}

const metricCards = computed(() => {
  if (mode.value === 'region') {
    return [
      { label: '营收', value: selectedProvince.value.revenue, color: visual.screenSecondary, code: '营' },
      { label: '区域利润', value: selectedProvince.value.profit, color: visual.screenAccent, code: '利' }
    ]
  }
  return [
    { label: '已实现业务规模', value: Number(fin.value.total_realized_scale || 0), color: visual.screenSecondary, code: '规' },
    { label: '已实现业务毛利润', value: Number(fin.value.total_gross_income || 0), color: visual.screenAccent, code: '毛' }
  ]
})

async function loadFinancial() {
  try {
    fin.value = await getFinancial()
  } catch {
    fin.value = { total_realized_scale: 0, total_gross_income: 0, ledger_profit: [] }
  }
}

let pollTimer = null
onMounted(async () => {
  tickClock()
  clockTimer = setInterval(tickClock, 1000)
  await loadFinancial()
  pollTimer = setInterval(loadFinancial, 20000)
})
onBeforeUnmount(() => {
  clearInterval(clockTimer)
  clearInterval(pollTimer)
})
</script>

<style scoped lang="scss">
.ds {
  box-sizing: border-box;
  color: var(--screen-text);
  font-family: var(--font-body);
  background:
    radial-gradient(900px 520px at 48% 42%, color-mix(in srgb, var(--screen-primary) 12%, transparent), transparent 70%),
    radial-gradient(600px 420px at 88% 16%, color-mix(in srgb, var(--screen-secondary) 8%, transparent), transparent 72%),
    var(--screen-bg);
}
.ds-embed { min-height: calc(100vh - 60px); margin: -20px; padding: 14px 18px 18px; }
.ds-full { min-height: 100vh; margin: 0; padding: 14px 20px 18px; }

.screen-head {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(380px, 1.4fr) minmax(220px, 1fr);
  align-items: center;
  padding: 6px 8px 14px;
  border-bottom: 1px solid var(--screen-border);
}
.head-title { margin: 0; text-align: center; line-height: 1.2; }
.title-cn { display: block; color: var(--screen-text); font-family: var(--font-display); font-size: clamp(20px, 1.65vw, 26px); font-weight: 800; letter-spacing: 3px; }
.title-en { display: block; margin-top: 5px; color: var(--screen-text-muted); font-size: 10px; letter-spacing: 4px; }
.head-side { min-width: 0; display: flex; align-items: center; color: var(--screen-text-muted); font-size: 12px; }
.head-side.right { justify-content: flex-end; gap: 4px; }
.head-side.left { gap: 2px; }
.clock { color: var(--screen-secondary); font-family: var(--font-data); font-size: 16px; font-weight: 700; letter-spacing: 1px; }
.sep { margin: 0 8px; color: var(--screen-border); }
.scr-btn { margin-left: 10px; color: var(--screen-text); border-color: var(--screen-border); background: var(--screen-surface); }
.dot { display: inline-block; width: 8px; height: 8px; margin-right: 4px; border-radius: 50%; }
.dot.online { background: var(--screen-secondary); box-shadow: 0 0 8px var(--screen-secondary); animation: statusPulse 1.6s infinite; }

.screen-body { margin-top: 14px; }
.map-stage {
  position: relative;
  min-height: 650px;
  overflow: hidden;
  border: 1px solid var(--screen-border);
  border-radius: var(--radius-md);
  background:
    linear-gradient(var(--screen-border) 1px, transparent 1px),
    linear-gradient(90deg, var(--screen-border) 1px, transparent 1px),
    color-mix(in srgb, var(--screen-bg) 82%, transparent);
  background-size: 56px 56px;
  box-shadow: var(--screen-shadow), inset 0 0 80px color-mix(in srgb, var(--screen-primary) 8%, transparent);
  isolation: isolate;
}
.ds-embed .map-stage { height: clamp(650px, calc(100vh - 156px), 840px); }
.ds-full .map-stage { height: calc(100vh - 106px); }
.map-stage::before {
  position: absolute;
  inset: 0;
  z-index: 0;
  content: '';
  pointer-events: none;
  background: radial-gradient(circle at 48% 54%, color-mix(in srgb, var(--screen-primary) 15%, transparent), transparent 46%);
}

.map-heading {
  position: absolute;
  top: 24px;
  left: 28px;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 12px;
  pointer-events: none;
}
.heading-mark {
  width: 5px;
  height: 42px;
  border-radius: var(--el-border-radius-round);
  background: linear-gradient(180deg, var(--screen-secondary), var(--screen-primary));
  box-shadow: 0 0 18px color-mix(in srgb, var(--screen-secondary) 62%, transparent);
}
.map-heading h2 { margin: 0; color: var(--screen-text); font-family: var(--font-display); font-size: clamp(20px, 1.8vw, 28px); letter-spacing: .12em; }
.map-heading p { margin: 5px 0 0; color: var(--screen-text-muted); font-family: var(--font-data); font-size: 9px; letter-spacing: .22em; }

.metrics-dock {
  position: absolute;
  top: 26px;
  right: 28px;
  z-index: 6;
  width: clamp(320px, 27vw, 410px);
  padding: 18px;
  border: 1px solid color-mix(in srgb, var(--screen-primary) 52%, transparent);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--screen-bg) 82%, transparent);
  box-shadow: 0 18px 48px color-mix(in srgb, var(--screen-bg) 76%, transparent), inset 0 1px 0 color-mix(in srgb, var(--screen-text) 10%, transparent);
  backdrop-filter: blur(16px);
  animation: dockIn .55s ease both;
}
.dock-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
.dock-head > div { display: flex; flex-direction: column; gap: 5px; }
.dock-eyebrow { color: var(--screen-text-muted); font-size: 11px; letter-spacing: .16em; }
.dock-head strong { color: var(--screen-text); font-family: var(--font-display); font-size: 18px; letter-spacing: .08em; }
.reset-button {
  padding: 5px 10px;
  color: var(--screen-secondary);
  border: 1px solid var(--screen-border);
  border-radius: var(--el-border-radius-round);
  background: transparent;
  cursor: pointer;
  transition: all var(--motion-base) ease;
}
.reset-button:hover { color: var(--screen-text); border-color: var(--screen-secondary); background: color-mix(in srgb, var(--screen-secondary) 12%, transparent); }
.metrics { display: grid; gap: 10px; }
.metric {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--screen-border);
  border-radius: var(--radius-sm);
  background: color-mix(in srgb, var(--screen-surface-strong) 84%, transparent);
  transition: transform var(--motion-base) ease, border-color var(--motion-base) ease;
}
.metric:hover { transform: translateX(-3px); border-color: color-mix(in srgb, var(--screen-secondary) 62%, transparent); }
.metric-code {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  color: var(--screen-bg);
  border-radius: 50%;
  background: linear-gradient(145deg, var(--screen-secondary), var(--screen-primary));
  box-shadow: 0 0 18px color-mix(in srgb, var(--screen-primary) 38%, transparent);
  font-weight: 850;
}
.metric-label { color: var(--screen-text-muted); font-size: 12px; letter-spacing: .05em; }
.metric-value { margin-top: 5px; font-family: var(--font-data); font-size: clamp(22px, 2vw, 31px); font-weight: 800; line-height: 1.05; text-shadow: 0 0 16px currentColor; white-space: nowrap; }
.metric-unit { margin-top: 5px; color: var(--screen-text-muted); font-size: 9px; letter-spacing: .1em; }
.dock-note { margin: 14px 2px 0; color: var(--screen-text-muted); font-size: 11px; line-height: 1.6; }

.map-guide {
  position: absolute;
  left: 28px;
  bottom: 22px;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 8px 12px;
  color: var(--screen-text-muted);
  border: 1px solid var(--screen-border);
  border-radius: var(--el-border-radius-round);
  background: color-mix(in srgb, var(--screen-bg) 74%, transparent);
  font-size: 11px;
  backdrop-filter: blur(10px);
  pointer-events: none;
}
.guide-pulse { width: 7px; height: 7px; border-radius: 50%; background: var(--screen-secondary); box-shadow: 0 0 0 0 color-mix(in srgb, var(--screen-secondary) 45%, transparent); animation: guidePulse 2s infinite; }

@keyframes statusPulse { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
@keyframes dockIn { from { opacity: 0; transform: translateY(-10px); } to { opacity: 1; transform: translateY(0); } }
@keyframes guidePulse { 70% { box-shadow: 0 0 0 9px transparent; } 100% { box-shadow: 0 0 0 0 transparent; } }

@media (max-width: 900px) {
  .screen-head { grid-template-columns: 1fr auto; }
  .head-title { grid-column: 1 / -1; grid-row: 1; margin-bottom: 10px; }
  .head-side { grid-row: 2; }
  .map-stage, .ds-embed .map-stage, .ds-full .map-stage { height: 820px; }
  .metrics-dock { top: auto; right: 18px; bottom: 18px; left: 18px; width: auto; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .map-guide { bottom: 270px; }
}

@media (max-width: 620px) {
  .ds-embed, .ds-full { padding: 10px; }
  .head-side.left { display: none; }
  .screen-head { grid-template-columns: 1fr; }
  .head-side.right { justify-content: center; }
  .map-heading { top: 18px; left: 18px; }
  .map-heading p, .map-guide { display: none; }
  .metrics { grid-template-columns: 1fr; }
  .map-stage, .ds-embed .map-stage, .ds-full .map-stage { height: 900px; }
}

@media (prefers-reduced-motion: reduce) {
  .dot.online, .guide-pulse, .metrics-dock { animation: none; }
  .metric, .reset-button { transition: none; }
}
</style>
