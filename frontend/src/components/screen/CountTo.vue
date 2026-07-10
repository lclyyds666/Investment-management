<template>
  <span class="count-to">{{ prefix }}{{ display }}{{ suffix }}</span>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  value: { type: Number, default: 0 },
  duration: { type: Number, default: 1600 },
  decimals: { type: Number, default: 0 },
  prefix: { type: String, default: '' },
  suffix: { type: String, default: '' },
  separator: { type: Boolean, default: true }
})

const display = ref('0')
let raf = null
let startTs = 0
let from = 0
let to = 0

function fmt(n) {
  const fixed = Number(n).toFixed(props.decimals)
  if (!props.separator) return fixed
  const [i, d] = fixed.split('.')
  const withSep = i.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return d ? `${withSep}.${d}` : withSep
}

// easeOutCubic
const ease = (t) => 1 - Math.pow(1 - t, 3)

function animate(ts) {
  if (!startTs) startTs = ts
  const p = Math.min(1, (ts - startTs) / props.duration)
  const cur = from + (to - from) * ease(p)
  display.value = fmt(cur)
  if (p < 1) {
    raf = requestAnimationFrame(animate)
  } else {
    display.value = fmt(to)
    raf = null
  }
}

function run(target) {
  cancelAnimationFrame(raf)
  from = parseFloat(String(display.value).replace(/,/g, '')) || 0
  to = Number(target) || 0
  startTs = 0
  raf = requestAnimationFrame(animate)
}

watch(() => props.value, (v) => run(v))
onMounted(() => run(props.value))
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<style scoped>
.count-to { font-variant-numeric: tabular-nums; }
</style>
