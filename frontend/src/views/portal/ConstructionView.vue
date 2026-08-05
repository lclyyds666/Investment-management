<template>
  <main class="construction-view portal-page">
    <section class="construction-view__content" aria-labelledby="construction-title">
      <span class="construction-view__icon" aria-hidden="true">
        <el-icon><Tools /></el-icon>
      </span>
      <p>业务系统</p>
      <h1 id="construction-title">{{ companyName }}</h1>
      <strong>建设中</strong>
      <el-button :icon="Back" @click="router.push({ name: 'PortalHome' })">返回工作平台</el-button>
    </section>
  </main>
</template>

<script setup>
import { computed } from 'vue'
import { Back, Tools } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const companyName = computed(() => String(route.meta.companyName || '业务系统'))
</script>

<style scoped>
.construction-view {
  display: grid;
  min-height: 100%;
  padding: clamp(28px, 7vh, 72px) clamp(18px, 5vw, 72px);
  place-items: center;
}

.construction-view__content {
  width: min(100%, 720px);
  padding-block: 42px;
  border-block: 1px solid var(--surface-border);
  text-align: center;
}

.construction-view__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border: 1px solid var(--surface-border-strong);
  border-radius: 8px;
  color: var(--brand-vermilion);
  background: var(--surface-muted);
  font-size: 25px;
}

p {
  margin: 22px 0 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: 650;
}

h1 {
  margin: 0;
  overflow-wrap: anywhere;
  color: var(--el-text-color-primary);
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1.45;
}

strong {
  display: block;
  margin: 16px 0 28px;
  color: var(--brand-vermilion);
  font-size: 16px;
  letter-spacing: 0;
}

@media (max-width: 520px) {
  h1 { font-size: 23px; }
}
</style>
