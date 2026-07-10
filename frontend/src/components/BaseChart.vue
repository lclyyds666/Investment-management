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

function render() {
  if (!chart.value && el.value) {
    chart.value = echarts.init(el.value)
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
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resize)
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
