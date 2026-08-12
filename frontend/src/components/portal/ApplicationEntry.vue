<template>
  <article
    class="application-entry"
    :class="[`application-entry--${application.code}`, { 'is-openable': canOpen, 'is-denied': isDenied }]"
    data-testid="application-entry"
    :role="canOpen ? 'link' : undefined"
    :tabindex="canOpen ? 0 : undefined"
    :aria-disabled="canOpen ? undefined : 'true'"
    @click="open"
    @keydown.enter.prevent="open"
    @keydown.space.prevent="open"
  >
    <div class="application-entry__heading">
      <span class="application-entry__icon" aria-hidden="true">
        <el-icon><OfficeBuilding /></el-icon>
      </span>
      <div class="application-entry__status">
        <span v-if="application.status === 'construction'" class="status-line">
          <el-icon><Tools /></el-icon>
          建设中
        </span>
        <span v-else-if="canOpen" class="status-line status-line--online">
          <span class="status-dot" aria-hidden="true"></span>
          运行中
        </span>
      </div>
    </div>

    <h2>{{ application.company_name }}</h2>

    <div class="application-entry__footer">
      <span v-if="isDenied" class="status-line status-line--denied">
        <el-icon><Lock /></el-icon>
        {{ application.denial_reason || '暂时无访问权限' }}
      </span>
      <span v-else-if="canOpen" class="application-entry__open">
        进入系统
        <el-icon><Right /></el-icon>
      </span>
      <span v-else class="application-entry__pending">暂未开放</span>
    </div>
  </article>
</template>

<script setup>
import { computed } from 'vue'
import { Lock, OfficeBuilding, Right, Tools } from '@element-plus/icons-vue'

const props = defineProps({
  application: {
    type: Object,
    required: true
  }
})

const emit = defineEmits(['open'])
const canOpen = computed(() => props.application.status === 'online' && props.application.accessible === true)
const isDenied = computed(() => props.application.accessible !== true)

function open() {
  if (canOpen.value) emit('open', props.application.route)
}
</script>

<style scoped>
.application-entry {
  --entry-accent: var(--brand-lake);
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: var(--portal-entry-min-height);
  padding: 22px;
  overflow: hidden;
  border: 1px solid var(--surface-border);
  border-radius: 8px;
  background: var(--surface-solid);
  box-shadow: var(--surface-shadow);
  transition: border-color var(--motion-fast) ease, box-shadow var(--motion-fast) ease, transform var(--motion-fast) ease;
}

.application-entry::before {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 4px;
  background: var(--entry-accent);
  content: '';
}

.application-entry--investment { --entry-accent: var(--brand-vermilion); }
.application-entry--supplymanagement { --entry-accent: var(--brand-jade); }
.application-entry--fundmanagement { --entry-accent: var(--brand-amber); }

.application-entry.is-openable {
  cursor: pointer;
}

.application-entry.is-openable:hover,
.application-entry.is-openable:focus-visible {
  border-color: var(--entry-accent);
  box-shadow: var(--surface-shadow-raised);
  transform: translateY(-2px);
}

.application-entry.is-denied {
  background: var(--surface-muted);
}

.application-entry__heading,
.application-entry__footer,
.status-line,
.application-entry__open {
  display: flex;
  align-items: center;
}

.application-entry__heading {
  justify-content: space-between;
  gap: 16px;
}

.application-entry__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border: 1px solid color-mix(in srgb, var(--entry-accent) 32%, transparent);
  border-radius: 6px;
  color: var(--entry-accent);
  background: color-mix(in srgb, var(--entry-accent) 9%, var(--surface-solid));
  font-size: 21px;
}

.application-entry__status {
  min-width: 0;
}

.status-line {
  gap: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: 650;
  line-height: 1.4;
}

.status-line--online {
  color: var(--el-color-success);
}

.status-line--denied {
  color: var(--el-text-color-secondary);
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

h2 {
  max-width: 100%;
  margin: 24px 0 18px;
  overflow-wrap: anywhere;
  color: var(--el-text-color-primary);
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 750;
  letter-spacing: 0;
  line-height: 1.5;
}

.application-entry__footer {
  justify-content: space-between;
  min-height: 24px;
  margin-top: auto;
}

.application-entry__open {
  gap: 6px;
  margin-left: auto;
  color: var(--entry-accent);
  font-size: 13px;
  font-weight: 700;
}

.application-entry__pending {
  color: var(--el-text-color-placeholder);
  font-size: 13px;
}

@media (prefers-reduced-motion: reduce) {
  .application-entry {
    transition: none;
  }
}
</style>
