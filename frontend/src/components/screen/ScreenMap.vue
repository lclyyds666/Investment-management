<template>
  <div class="screen-map">
    <div ref="element" class="map-el" :style="{ height }"></div>
    <div v-if="fallback" class="map-fallback">
      地图底图加载失败，请检查本地地图资源后重试
    </div>
  </div>
</template>

<script>
import { formatWanFromYuan as formatScreenMapMoneyValue } from '@/utils/money'

export function formatScreenMapMoney(value) {
  return formatScreenMapMoneyValue(value)
}
</script>

<script setup>
import { ref, shallowRef, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import * as echarts from 'echarts'
import { chartVisualTokens as visual } from '@/utils/visualTokens'

const props = defineProps({
  height: { type: String, default: '100%' },
  provinceData: { type: Array, default: () => [] },
  selectedProvince: { type: String, default: '' }
})
const emit = defineEmits(['province-click'])

const PROVINCE_COORDS = {
  山东省: [117.02, 36.67],
  福建省: [119.30, 26.08],
  贵州省: [106.71, 26.58],
  河南省: [113.62, 34.75],
  山西省: [112.55, 37.87]
}
const PROVINCE_SUFFIX = /(省|市|壮族自治区|回族自治区|维吾尔自治区|自治区|特别行政区)$/

const element = ref(null)
const chart = shallowRef(null)
const fallback = ref(false)
let provinceNames = []

function provinceCore(name = '') {
  return String(name).replace(PROVINCE_SUFFIX, '')
}

function matchBusinessProvince(name) {
  const core = provinceCore(name)
  return props.provinceData.find((item) => provinceCore(item.name) === core)
}

function mapProvinceName(name) {
  const core = provinceCore(name)
  return provinceNames.find((item) => provinceCore(item) === core) || name
}

async function ensureMap() {
  const registered = echarts.getMap('china')
  if (registered) {
    provinceNames = (registered.geoJSON?.features || [])
      .map((feature) => feature.properties?.name)
      .filter(Boolean)
    return true
  }
  const sources = [
    '/geo/china.json',
    'https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json'
  ]
  for (const url of sources) {
    try {
      const response = await fetch(url)
      if (!response.ok) continue
      const geoJson = await response.json()
      echarts.registerMap('china', geoJson)
      provinceNames = (geoJson.features || [])
        .map((feature) => feature.properties?.name)
        .filter(Boolean)
      return true
    } catch {
      // 继续尝试备用底图。
    }
  }
  return false
}

function buildOption() {
  const maximumRevenue = Math.max(
    1,
    ...props.provinceData.map((item) => Number(item.revenue) || 0)
  )
  const mapData = provinceNames.map((name) => {
    const business = matchBusinessProvince(name)
    return {
      name,
      value: Number(business?.revenue || 0),
      revenue: Number(business?.revenue || 0),
      profit: Number(business?.profit || 0),
      scenicCount: Number(business?.scenicCount || 0)
    }
  })
  const nodes = props.provinceData
    .filter((item) => PROVINCE_COORDS[item.name])
    .map((item) => ({
      name: item.name,
      province: item.name,
      revenue: Number(item.revenue || 0),
      profit: Number(item.profit || 0),
      scenicCount: Number(item.scenicCount || 0),
      value: [...PROVINCE_COORDS[item.name], Number(item.revenue || 0)]
    }))
  const hubCoord = PROVINCE_COORDS['山东省']
  const lines = nodes
    .filter((item) => item.province !== '山东省')
    .map((item) => ({
      name: item.province,
      coords: [hubCoord, item.value.slice(0, 2)],
      lineStyle: {
        width: 1 + Math.min(item.revenue / maximumRevenue, 1) * 2.5,
        opacity: item.revenue > 0 ? 0.66 : 0.22
      }
    }))

  const selectedMapName = props.selectedProvince
    ? mapProvinceName(props.selectedProvince)
    : ''

  return {
    backgroundColor: 'transparent',
    animationDuration: 900,
    animationDurationUpdate: 650,
    tooltip: {
      trigger: 'item',
      backgroundColor: visual.screenTooltip,
      borderColor: visual.screenPrimary,
      padding: [10, 12],
      textStyle: { color: visual.screenText },
      formatter: (params) => {
        const province = params.data?.province || params.name
        const business = matchBusinessProvince(province)
        return [
          `<strong>${province}</strong>`,
          `营收：${formatScreenMapMoney(business?.revenue)}`,
          `区域利润：${formatScreenMapMoney(business?.profit)}`,
          `景区数量：${Number(business?.scenicCount || 0)}`
        ].join('<br/>')
      }
    },
    visualMap: {
      show: false,
      min: 0,
      max: maximumRevenue,
      seriesIndex: 0,
      inRange: { color: visual.screenMapRamp }
    },
    geo: {
      map: 'china',
      roam: true,
      zoom: 1.18,
      center: [104.5, 36.2],
      scaleLimit: { min: 0.85, max: 4 },
      label: { show: false },
      regions: selectedMapName ? [{
        name: selectedMapName,
        itemStyle: {
          areaColor: visual.screenMapAreaEmphasis,
          borderColor: visual.screenAccent,
          borderWidth: 1.8
        }
      }] : [],
      itemStyle: {
        areaColor: visual.screenMapArea,
        borderColor: visual.screenPrimary,
        borderWidth: 1,
        shadowBlur: 24,
        shadowColor: visual.screenPrimarySoft,
        shadowOffsetY: 10
      },
      emphasis: {
        label: { show: true, color: visual.screenText, fontSize: 11 },
        itemStyle: {
          areaColor: visual.screenMapAreaEmphasis,
          borderColor: visual.screenAccent,
          borderWidth: 1.6,
          shadowBlur: 28,
          shadowColor: visual.screenPrimary
        }
      }
    },
    series: [
      {
        name: '省份营收',
        type: 'map',
        map: 'china',
        geoIndex: 0,
        data: mapData
      },
      {
        name: '业务脉冲',
        type: 'lines',
        coordinateSystem: 'geo',
        zlevel: 2,
        silent: true,
        effect: {
          show: true,
          period: 5.2,
          trailLength: 0.45,
          symbol: 'circle',
          symbolSize: 5,
          color: visual.screenSecondary
        },
        lineStyle: {
          color: visual.screenPrimary,
          curveness: 0.22
        },
        data: lines
      },
      {
        name: '景区业务节点',
        type: 'effectScatter',
        coordinateSystem: 'geo',
        zlevel: 3,
        rippleEffect: { brushType: 'stroke', scale: 4.8, period: 3.8 },
        symbolSize: (value) => 10 + Math.min(Number(value[2] || 0) / maximumRevenue, 1) * 20,
        itemStyle: {
          color: visual.screenSecondary,
          shadowBlur: 18,
          shadowColor: visual.screenSecondary
        },
        label: {
          show: true,
          formatter: '{b}',
          position: 'right',
          distance: 8,
          color: visual.screenText,
          fontSize: 11,
          textShadowBlur: 8,
          textShadowColor: visual.screenTooltip
        },
        data: nodes
      },
      {
        name: '数据中枢',
        type: 'effectScatter',
        coordinateSystem: 'geo',
        zlevel: 4,
        silent: true,
        rippleEffect: { brushType: 'stroke', scale: 6.2, period: 4.6 },
        symbolSize: 17,
        itemStyle: {
          color: visual.screenAccent,
          shadowBlur: 22,
          shadowColor: visual.screenAccent
        },
        data: [{ name: '数据中枢', value: [...hubCoord, maximumRevenue] }]
      }
    ]
  }
}

async function render() {
  if (!element.value) return
  if (!chart.value) chart.value = echarts.init(element.value)
  const available = await ensureMap()
  fallback.value = !available
  if (!available) {
    chart.value.clear()
    return
  }
  chart.value.setOption(buildOption(), true)
  chart.value.off('click')
  chart.value.on('click', (params) => {
    if (params.seriesType === 'lines') return
    const rawName = params.data?.province || params.name
    if (!rawName || rawName === '数据中枢') return
    emit('province-click', matchBusinessProvince(rawName)?.name || rawName)
  })
}

function resize() {
  chart.value?.resize()
}

watch(
  () => [props.provinceData, props.selectedProvince],
  () => render(),
  { deep: true }
)

onMounted(async () => {
  await nextTick()
  await render()
  window.addEventListener('resize', resize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  chart.value?.dispose()
  chart.value = null
})
</script>

<style scoped>
.screen-map {
  position: relative;
  z-index: 1;
  width: 100%;
  height: 100%;
}
.map-el { width: 100%; }
.map-fallback {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 24px;
  color: var(--screen-text-muted);
  font-size: 13px;
  text-align: center;
  pointer-events: none;
}
</style>
