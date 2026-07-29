<template>
  <div ref="el" class="base-chart" :style="{ height }"></div>
</template>

<script setup>
import { ref, shallowRef, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '360px' }
})

const el = ref(null)
const chart = shallowRef(null)
let themeObserver = null

function cssToken(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

function currentTheme() {
  const textPrimary = cssToken('--el-text-color-primary')
  const textSecondary = cssToken('--el-text-color-secondary')
  const border = cssToken('--el-border-color-lighter')
  const surface = cssToken('--el-bg-color-overlay')
  return {
    backgroundColor: 'transparent',
    color: [
      cssToken('--el-color-primary'),
      cssToken('--el-color-success'),
      cssToken('--el-color-warning'),
      cssToken('--el-color-danger'),
      cssToken('--el-color-info')
    ],
    textStyle: { color: textPrimary, fontFamily: cssToken('--font-body') },
    title: { textStyle: { color: textPrimary }, subtextStyle: { color: textSecondary } },
    legend: { textStyle: { color: textSecondary } },
    tooltip: {
      backgroundColor: surface,
      borderColor: border,
      textStyle: { color: textPrimary }
    },
    categoryAxis: {
      axisLine: { lineStyle: { color: border } },
      axisTick: { lineStyle: { color: border } },
      axisLabel: { color: textSecondary },
      splitLine: { lineStyle: { color: border } }
    },
    valueAxis: {
      axisLine: { lineStyle: { color: border } },
      axisTick: { lineStyle: { color: border } },
      axisLabel: { color: textSecondary },
      splitLine: { lineStyle: { color: border } }
    }
  }
}

function render(recreate = false) {
  if (recreate && chart.value) {
    chart.value.dispose()
    chart.value = null
  }
  if (!chart.value && el.value) {
    chart.value = echarts.init(el.value, currentTheme())
  }
  chart.value?.setOption(props.option, true)
}

function resize() {
  chart.value?.resize()
}

onMounted(async () => {
  await nextTick()
  render()
  window.addEventListener('resize', resize)
  themeObserver = new MutationObserver(() => render(true))
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
  themeObserver?.disconnect()
  themeObserver = null
  chart.value?.dispose()
  chart.value = null
})

// option 变化时重绘
watch(() => props.option, render, { deep: true })
</script>

<style scoped>
.base-chart {
  width: 100%;
}
</style>
