<template>
  <main class="portal-home portal-page">
    <section data-testid="assistant-region" class="assistant-region" aria-label="AI 智能助手">
      <div class="assistant-placeholder" aria-hidden="true">
        <el-skeleton :rows="5" animated />
      </div>
    </section>

    <section data-testid="application-region" class="application-region" aria-label="业务系统">
      <div class="application-region__heading">
        <div>
          <p class="section-kicker">业务系统</p>
          <h1>工作入口</h1>
        </div>
        <el-button v-if="loadFailed" :icon="Refresh" @click="loadContext">重新加载</el-button>
      </div>

      <div v-if="portalStore.applications.length" class="application-grid">
        <ApplicationEntry
          v-for="application in portalStore.applications"
          :key="application.code"
          :application="application"
          @open="router.push($event)"
        />
      </div>
      <el-alert
        v-else-if="loadFailed"
        title="业务系统入口加载失败"
        type="error"
        :closable="false"
        show-icon
      />
      <div v-else class="application-grid application-grid--loading" aria-label="业务系统加载中">
        <el-skeleton v-for="index in 3" :key="index" :rows="3" animated />
      </div>
    </section>
  </main>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import ApplicationEntry from '@/components/portal/ApplicationEntry.vue'
import { usePortalStore } from '@/store/portal'

const router = useRouter()
const portalStore = usePortalStore()
const loadFailed = ref(false)

async function loadContext() {
  loadFailed.value = false
  try {
    await portalStore.loadPortalContext(true)
  } catch {
    loadFailed.value = true
  }
}

onMounted(async () => {
  if (!portalStore.applications.length) await loadContext()
})
</script>

<style scoped>
.portal-home {
  padding: 22px clamp(16px, 2.4vw, 36px) 32px;
}

.assistant-region {
  display: flex;
  align-items: center;
  min-height: var(--portal-assistant-height);
  padding: clamp(24px, 4vw, 56px);
  border-block: 1px solid var(--surface-border);
  background: color-mix(in srgb, var(--surface-solid) 88%, transparent);
}

.assistant-placeholder {
  width: min(100%, 980px);
  margin-inline: auto;
}

.application-region {
  padding-top: 24px;
}

.application-region__heading {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.section-kicker {
  margin: 0 0 3px;
  color: var(--brand-vermilion);
  font-family: var(--font-data);
  font-size: 11px;
  font-weight: 750;
  letter-spacing: 0;
}

h1 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-family: var(--font-display);
  font-size: 21px;
  font-weight: 780;
  letter-spacing: 0;
}

.application-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.application-grid--loading > * {
  min-height: var(--portal-entry-min-height);
  padding: 22px;
  border: 1px solid var(--surface-border);
  border-radius: 8px;
  background: var(--surface-solid);
}

@media (max-width: 960px) {
  .application-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 719px) {
  .portal-home {
    padding: 14px 12px 24px;
  }

  .assistant-region {
    min-height: 380px;
    padding: 24px 18px;
  }

  .application-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .application-region__heading {
    align-items: flex-start;
  }
}
</style>
