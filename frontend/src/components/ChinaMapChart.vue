<template>
  <div class="china-map">
    <div ref="el" class="map-el" :style="{ height }"></div>
    <div v-if="fallback" class="map-tip">地图资源加载失败（可能离线），已降级为业务分布条形图；点击条目同样可联动。</div>
  </div>
</template>

<script setup>
import { ref, shallowRef, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  data: { type: Array, default: () => [] }, // [{name:'山东省', value: 1234}]
  height: { type: String, default: '460px' }
})
const emit = defineEmits(['province-click'])

const el = ref(null)
const chart = shallowRef(null)
const fallback = ref(false)

// 全局仅注册一次中国地图
let mapReady = false
async function ensureMap() {
  if (mapReady || echarts.getMap('china')) { mapReady = true; return true }
  // 优先本地自托管 GeoJSON（离线可用），失败再退阿里云公网
  const sources = [
    '/geo/china.json',
    'https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json'
  ]
  for (const url of sources) {
    try {
      const resp = await fetch(url)
      if (!resp.ok) continue
      echarts.registerMap('china', await resp.json())
      mapReady = true
      return true
    } catch (e) { /* 尝试下一个来源 */ }
  }
  return false
}

function values() {
  return props.data.map((d) => Number(d.value) || 0)
}
function mapOption() {
  const max = Math.max(1, ...values())
  return {
    tooltip: { trigger: 'item', formatter: (p) => `${p.name}<br/>业务额：¥${Number(p.value || 0).toLocaleString()}` },
    visualMap: {
      min: 0, max, left: 16, bottom: 16, calculable: true,
      inRange: { color: ['#e6f0ff', '#7aa7f0', '#3f6ad8', '#1f3a93'] },
      text: ['高', '低'], textStyle: { color: '#606266' }
    },
    series: [{
      name: '业务概况', type: 'map', map: 'china', roam: true,
      emphasis: { label: { show: true }, itemStyle: { areaColor: '#f5c542' } },
      itemStyle: { borderColor: '#c9d4ea' },
      data: props.data
    }]
  }
}
function barOption() {
  const sorted = [...props.data].sort((a, b) => a.value - b.value)
  return {
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 90, right: 30, top: 20, bottom: 20 },
    xAxis: { type: 'value', axisLabel: { formatter: (v) => v / 10000 + '万' } },
    yAxis: { type: 'category', data: sorted.map((d) => d.name) },
    series: [{
      type: 'bar', data: sorted.map((d) => d.value),
      itemStyle: { color: '#3f6ad8', borderRadius: [0, 4, 4, 0] }, barMaxWidth: 18
    }]
  }
}

async function render() {
  if (!el.value) return
  if (!chart.value) chart.value = echarts.init(el.value)
  const ok = await ensureMap()
  fallback.value = !ok
  chart.value.setOption(ok ? mapOption() : barOption(), true)
  chart.value.off('click')
  chart.value.on('click', (p) => { if (p.name) emit('province-click', p.name) })
}
function resize() { chart.value?.resize() }

onMounted(async () => { await nextTick(); render(); window.addEventListener('resize', resize) })
onBeforeUnmount(() => { window.removeEventListener('resize', resize); chart.value?.dispose(); chart.value = null })
watch(() => props.data, render, { deep: true })
</script>

<style scoped>
.china-map { width: 100%; }
.map-el { width: 100%; }
.map-tip { margin-top: 6px; font-size: 12px; color: #e6a23c; text-align: center; }
</style>
