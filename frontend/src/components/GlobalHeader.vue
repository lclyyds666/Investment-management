<template>
  <header class="global-header">
    <div class="global-header__identity">
      <span class="global-header__rail" aria-hidden="true"></span>
      <div class="global-header__titles">
        <span class="global-header__title">山东出版投资有限公司工作平台</span>
        <span v-if="contextLabel" class="global-header__context">{{ contextLabel }}</span>
      </div>
    </div>

    <div class="global-header__actions">
      <ThemeToggle />
      <UserDropdown />
      <el-button
        v-if="showAssistantAction"
        class="assistant-action btn-ai"
        aria-label="AI 助手"
        @click="openAssistant"
      >
        <el-icon><ChatDotRound /></el-icon>
        <span>AI 助手</span>
      </el-button>
    </div>
  </header>
</template>

<script setup>
import { ChatDotRound } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import ThemeToggle from '@/components/ThemeToggle.vue'
import UserDropdown from '@/components/UserDropdown.vue'

defineProps({
  contextLabel: { type: String, default: '' },
  showAssistantAction: { type: Boolean, default: false }
})

const router = useRouter()
const openAssistant = () => router.push({ name: 'PortalHome' })
</script>

<style scoped lang="scss">
.global-header {
  position: relative;
  z-index: 10;
  display: grid;
  flex: 0 0 72px;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  width: 100%;
  height: 72px;
  min-width: 0;
  padding: 0 clamp(16px, 1.7vw, 30px);
  border-bottom: 1px solid var(--chrome-header-border);
  background: var(--chrome-header-bg);
  box-shadow: var(--chrome-header-shadow);
  backdrop-filter: blur(16px);
  transition: background-color var(--motion-base) ease, border-color var(--motion-base) ease;
}

.global-header__identity {
  display: flex;
  align-items: center;
  min-width: 0;
}

.global-header__rail {
  flex: 0 0 4px;
  width: 4px;
  height: 38px;
  margin-right: 12px;
  border-radius: 0 var(--radius-xs) var(--radius-xs) 0;
  background: var(--divider-rail);
}

.global-header__titles {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.global-header__title,
.global-header__context {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.global-header__title {
  color: var(--chrome-title-color);
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 750;
  letter-spacing: 0;
}

.global-header__context {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-family: var(--font-body);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0;
}

.global-header__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  margin-left: 16px;
}

.assistant-action {
  flex: 0 0 auto;
  min-width: 92px;
}

.assistant-action:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring) !important;
}

@media (max-width: 760px) {
  .global-header {
    padding-inline: 12px;
  }

  .global-header__rail {
    margin-right: 8px;
  }

  .global-header__title {
    font-size: 14px;
  }

  .global-header__context {
    display: none;
  }

  .global-header__actions {
    gap: 6px;
    margin-left: 8px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .global-header {
    transition: none;
  }
}
</style>
