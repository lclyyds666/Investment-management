<template>
  <el-container class="portal-layout" direction="vertical">
    <GlobalHeader :context-label="contextLabel" />
    <el-main class="portal-layout__main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import GlobalHeader from '@/components/GlobalHeader.vue'

const route = useRoute()
const contextLabel = computed(() => String(route.meta.companyName || ''))
</script>

<style scoped>
.portal-layout {
  width: 100%;
  height: 100%;
  min-width: 0;
}

.portal-layout__main {
  min-height: 0;
  overflow-y: auto;
}
</style>
