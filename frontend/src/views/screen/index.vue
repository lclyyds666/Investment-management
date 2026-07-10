<template>
  <div class="screen-page">
    <DataScreen fullscreen />
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import DataScreen from '@/components/screen/DataScreen.vue'

const router = useRouter()

function onKey(e) {
  // Esc 退出全屏投放，返回工作台
  if (e.key === 'Escape' && !document.fullscreenElement) router.push('/')
}

onMounted(() => {
  // 自动请求浏览器全屏，达到大屏投放效果（失败则维持网页全屏）
  document.documentElement.requestFullscreen?.().catch(() => {})
  window.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {})
})
</script>

<style scoped>
.screen-page {
  position: fixed;
  inset: 0;
  z-index: 3000;
  overflow: auto;
  background: #000a1f;
}
</style>
