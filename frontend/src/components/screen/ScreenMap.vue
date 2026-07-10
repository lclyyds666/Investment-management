<template>
  <div class="screen-map">
    <div ref="el" class="map-el" :style="{ height }"></div>
    <div v-if="fallback" class="map-fallback">地图资源离线，天眼视图暂不可用（其余大屏功能正常）</div>
  </div>
</template>

<script setup>
import { ref, shallowRef, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, default: () => [] }, // [{name, value}]
  hub: { type: String, default: '山东省' },
  height: { type: String, default: '620px' }
})
const emit = defineEmits(['province-click'])

// 省份经纬度（近似省会坐标）
const GEO = {
  山东省: [117.0, 36.65], 广东省: [113.28, 23.13], 江苏省: [118.78, 32.04],
  浙江省: [120.15, 30.28], 北京市: [116.40, 39.90], 上海市: [121.47, 31.23],
  湖北省: [114.31, 30.52], 河南省: [113.65, 34.76], 四川省: [104.06, 30.67],
  河北省: [114.50, 38.05], 福建省: [119.30, 26.08], 辽宁省: [123.43, 41.80]
}

const el = ref(null)
const chart = shallowRef(null)
const fallback = ref(false)

async function ensureMap() {
  if (echarts.getMap('china')) return true
  try {
    const resp = await fetch('https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json')
    if (!resp.ok) throw new Error('fail')
    echarts.registerMap('china', await resp.json())
    return true
  } catch (e) { return false }
}

function buildOption() {
  const max = Math.max(1, ...props.data.map((d) => d.value))
  const scatter = props.data
    .filter((d) => GEO[d.name])
    .map((d) => ({ name: d.name, value: [...GEO[d.name], d.value] }))
  const hubCoord = GEO[props.hub] || GEO['山东省']
  const lines = props.data
    .filter((d) => GEO[d.name] && d.name !== props.hub)
    .map((d) => ({ coords: [hubCoord, GEO[d.name]], val: d.value }))

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(4,20,48,0.9)', borderColor: '#1c9be6', textStyle: { color: '#cfe8ff' },
      formatter: (p) => (p.seriesType === 'effectScatter'
        ? `${p.name}<br/>业务额：¥${Number(p.value[2] || 0).toLocaleString()}` : p.name)
    },
    geo: {
      map: 'china', roam: true, zoom: 1.15,
      label: { show: false },
      itemStyle: {
        areaColor: 'rgba(9,34,74,0.75)', borderColor: 'rgba(44,225,192,0.35)', borderWidth: 1
      },
      emphasis: {
        label: { show: true, color: '#eafcff' },
        itemStyle: { areaColor: 'rgba(28,155,230,0.45)' }
      }
    },
    series: [
      {
        name: '业务额', type: 'map', map: 'china', geoIndex: 0,
        data: props.data
      },
      {
        name: '物流飞线', type: 'lines', coordinateSystem: 'geo', zlevel: 2,
        effect: { show: true, period: 5, trailLength: 0.55, symbol: 'arrow', symbolSize: 7, color: '#2de1c2' },
        lineStyle: { color: '#39c5ff', width: 1.2, opacity: 0.55, curveness: 0.25 },
        data: lines
      },
      {
        name: '业务节点', type: 'effectScatter', coordinateSystem: 'geo', zlevel: 3,
        rippleEffect: { brushType: 'stroke', scale: 4 },
        symbolSize: (val) => 6 + (val[2] / max) * 18,
        itemStyle: { color: '#2de1c2', shadowBlur: 12, shadowColor: '#2de1c2' },
        label: { show: true, formatter: '{b}', position: 'right', color: '#bfefff', fontSize: 10 },
        data: scatter
      },
      {
        name: '中枢', type: 'effectScatter', coordinateSystem: 'geo', zlevel: 4,
        rippleEffect: { brushType: 'stroke', scale: 6 },
        symbolSize: 16,
        itemStyle: { color: '#ffd34e', shadowBlur: 16, shadowColor: '#ffd34e' },
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
  chart.value.on('click', (p) => { if (p.name) emit('province-click', p.name) })
}
function resize() { chart.value?.resize() }

onMounted(async () => { await nextTick(); render(); window.addEventListener('resize', resize) })
onBeforeUnmount(() => { window.removeEventListener('resize', resize); chart.value?.dispose(); chart.value = null })
watch(() => props.data, render, { deep: true })
</script>

<style scoped>
.screen-map { width: 100%; position: relative; }
.map-el { width: 100%; }
.map-fallback {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  color: #7fa8d0; font-size: 13px;
}
</style>
