<template>
  <div class="screen-map">
    <div ref="el" class="map-el" :style="{ height }"></div>
    <div v-if="fallback" class="map-fallback">地图底图加载失败，天眼视图暂不可用（其余大屏功能正常）</div>
    <div v-else-if="loaded && !points.length" class="map-empty">
      暂无项目点位——请在【经营数据】页上传项目统计表，上传后地图将自动上屏
    </div>
  </div>
</template>

<script setup>
import { ref, shallowRef, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts'
import { getProjectsGeo } from '@/api/operation'

const props = defineProps({
  hub: { type: String, default: '山东省' },
  height: { type: String, default: '620px' },
  // 轮询间隔：上传新数据后大屏自动上屏（与审批跑马灯同款机制）
  pollMs: { type: Number, default: 30000 }
})
const emit = defineEmits(['province-click'])

// 中枢省经纬度（仅用于飞线汇聚点，与后端 gazetteer 一致）
const HUB_GEO = {
  山东省: [117.0, 36.65], 广东省: [113.28, 23.13], 江苏省: [118.78, 32.04],
  浙江省: [120.15, 30.28], 北京市: [116.41, 39.90], 上海市: [121.47, 31.23]
}

const el = ref(null)
const chart = shallowRef(null)
const fallback = ref(false)
const loaded = ref(false)
const points = ref([])      // [{ city, province, coord:[lng,lat], value, invested, realized, projects }]
let version = ''
let timer = null

// —— 底图：优先本地自托管 GeoJSON（离线可用），失败再退阿里云公网 —— //
async function ensureMap() {
  if (echarts.getMap('china')) return true
  const sources = [
    '/geo/china.json',
    'https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json'
  ]
  for (const url of sources) {
    try {
      const resp = await fetch(url)
      if (!resp.ok) continue
      echarts.registerMap('china', await resp.json())
      return true
    } catch (e) { /* 尝试下一个来源 */ }
  }
  return false
}

// —— 数据：从数据库读取已入库项目点位；version 变化才重绘 —— //
async function fetchGeo(force = false) {
  try {
    const res = await getProjectsGeo(props.hub)
    if (!force && res.version === version) return false
    version = res.version
    points.value = res.points || []
    return true
  } catch (e) {
    return false
  } finally {
    loaded.value = true
  }
}

function buildOption() {
  const pts = points.value
  const max = Math.max(1, ...pts.map((p) => Number(p.value) || 0))

  // 省级填色：由城市点位按省聚合而来（数据驱动，非 mock）
  const provAgg = {}
  pts.forEach((p) => {
    if (!p.province) return
    provAgg[p.province] = (provAgg[p.province] || 0) + (Number(p.value) || 0)
  })
  const provinceData = Object.entries(provAgg).map(([name, value]) => ({ name, value }))
  const provMax = Math.max(1, ...provinceData.map((d) => d.value))

  const scatter = pts.map((p) => ({
    name: p.city,
    value: [...p.coord, Number(p.value) || 0],
    projects: p.projects || [],
    invested: p.invested, realized: p.realized
  }))

  const hubCoord = HUB_GEO[props.hub] || HUB_GEO['山东省']
  // 飞线：金额越大越显眼（线宽 1→6、透明度 0.35→0.9）
  const lines = pts
    .filter((p) => p.province !== props.hub)
    .map((p) => {
      const ratio = (Number(p.value) || 0) / max
      return {
        coords: [hubCoord, p.coord],
        lineStyle: { width: 1 + ratio * 5, opacity: 0.35 + ratio * 0.55 }
      }
    })

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(4,20,48,0.9)', borderColor: '#1c9be6', textStyle: { color: '#cfe8ff' },
      formatter: (p) => {
        if (p.seriesType === 'effectScatter') {
          const projs = (p.data.projects || []).join('、') || '—'
          return `${p.name}<br/>投入(现存规模)：¥${Number(p.value[2] || 0).toLocaleString()}`
            + `<br/>回款：¥${Number(p.data.realized || 0).toLocaleString()}`
            + `<br/>项目：${projs}`
        }
        return p.name
      }
    },
    geo: {
      map: 'china', roam: true, zoom: 1.15,
      label: { show: false },
      itemStyle: { areaColor: 'rgba(9,34,74,0.75)', borderColor: 'rgba(44,225,192,0.35)', borderWidth: 1 },
      emphasis: { label: { show: true, color: '#eafcff' }, itemStyle: { areaColor: 'rgba(28,155,230,0.45)' } }
    },
    visualMap: {
      show: provinceData.length > 0, min: 0, max: provMax, calculable: false,
      left: 12, bottom: 12, itemWidth: 10, itemHeight: 60,
      inRange: { color: ['rgba(9,34,74,0.4)', 'rgba(28,155,230,0.55)', 'rgba(45,225,194,0.75)'] },
      text: ['高', '低'], textStyle: { color: '#7fa8d0' }, seriesIndex: 0
    },
    series: [
      { name: '业务额', type: 'map', map: 'china', geoIndex: 0, data: provinceData },
      {
        name: '物流飞线', type: 'lines', coordinateSystem: 'geo', zlevel: 2,
        effect: { show: true, period: 5, trailLength: 0.55, symbol: 'arrow', symbolSize: 7, color: '#2de1c2' },
        lineStyle: { color: '#39c5ff', curveness: 0.25 },
        data: lines
      },
      {
        name: '业务节点', type: 'effectScatter', coordinateSystem: 'geo', zlevel: 3,
        rippleEffect: { brushType: 'stroke', scale: 4 },
        symbolSize: (val) => 8 + (val[2] / max) * 26,
        itemStyle: { color: '#2de1c2', shadowBlur: 12, shadowColor: '#2de1c2' },
        label: { show: true, formatter: '{b}', position: 'right', color: '#bfefff', fontSize: 10 },
        data: scatter
      },
      {
        name: '中枢', type: 'effectScatter', coordinateSystem: 'geo', zlevel: 4,
        rippleEffect: { brushType: 'stroke', scale: 6 },
        symbolSize: 16,
        itemStyle: { color: '#ffd34e', shadowBlur: 16, shadowColor: '#ffd34e' },
        label: { show: true, formatter: props.hub, position: 'top', color: '#ffe89a', fontSize: 11 },
        data: [{ name: props.hub, value: [...hubCoord, max] }]
      }
    ]
  }
}

async function render() {
  if (!el.value) return
  if (!chart.value) chart.value = echarts.init(el.value)
  const ok = await ensureMap()
  fallback.value = !ok
  if (!ok) { chart.value.clear(); return }
  chart.value.setOption(buildOption(), true)
  chart.value.off('click')
  chart.value.on('click', (p) => {
    // 点击城市点位联动其所属省；点击省份直接联动
    const name = p.data?.province || p.name
    if (name) emit('province-click', name)
  })
}

function resize() { chart.value?.resize() }

async function poll() {
  const changed = await fetchGeo()
  if (changed) render()
}

onMounted(async () => {
  await nextTick()
  await fetchGeo(true)
  await render()
  window.addEventListener('resize', resize)
  timer = setInterval(poll, props.pollMs)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  if (timer) clearInterval(timer)
  chart.value?.dispose(); chart.value = null
})
</script>

<style scoped>
.screen-map { width: 100%; position: relative; }
.map-el { width: 100%; }
.map-fallback, .map-empty {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: #7fa8d0; font-size: 13px; text-align: center; padding: 0 24px; pointer-events: none;
}
</style>
