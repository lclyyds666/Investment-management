<template>
  <el-container class="system-layout">
    <el-aside :width="collapsed ? '64px' : '220px'" class="system-sidebar" :class="{ collapsed }">
      <div class="system-brand" aria-label="系统管理">
        <span class="system-seal">SD</span>
        <span v-show="!collapsed" class="system-brand__copy">
          <strong>系统管理</strong>
          <small>GOVERNANCE LEDGER</small>
        </span>
      </div>
      <el-menu
        :default-active="route.path"
        :collapse="collapsed"
        :collapse-transition="false"
        router
        background-color="transparent"
        text-color="var(--chrome-menu-text)"
        active-text-color="var(--chrome-menu-active-text)"
      >
        <el-menu-item v-for="item in menus" :key="item.path" :index="item.path">
          <el-icon><component :is="item.meta.icon" /></el-icon>
          <span>{{ item.meta.title }}</span>
        </el-menu-item>
      </el-menu>
      <button v-if="!compactViewport" class="collapse-bar" type="button" @click="toggleCollapsed">
        <el-icon><component :is="collapsed ? 'Expand' : 'Fold'" /></el-icon>
        <span v-show="!collapsed">收起菜单</span>
      </button>
    </el-aside>
    <el-container direction="vertical" class="system-content">
      <GlobalHeader context-label="治理与权限台账" />
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePortalStore } from '@/store/portal'
import GlobalHeader from '@/components/GlobalHeader.vue'

const route = useRoute()
const router = useRouter()
const portalStore = usePortalStore()
const compactViewport = ref(window.innerWidth <= 760)
const manuallyCollapsed = ref(localStorage.getItem('system_sidebar_collapsed') === '1')
const collapsed = computed(() => compactViewport.value || manuallyCollapsed.value)
const hasDirectoryPermission = computed(() => portalStore.isSuperuser || (
  portalStore.permissions.permissions || []
).some(({ code }) => code === 'organization.directory.view'))

const menus = computed(() => {
  const root = router.options.routes.find(item => item.path === '/system')
  return (root?.children || [])
    .filter(item => item.meta?.title)
    .filter(item => !item.meta.requiresSuperuser || portalStore.isSuperuser)
    .filter(item => !item.meta.permission || hasDirectoryPermission.value)
    .map(item => ({ ...item, path: router.resolve({ name: item.name }).path }))
})

function syncViewport() {
  compactViewport.value = window.innerWidth <= 760
}

function toggleCollapsed() {
  manuallyCollapsed.value = !manuallyCollapsed.value
  localStorage.setItem('system_sidebar_collapsed', manuallyCollapsed.value ? '1' : '0')
}

onMounted(() => window.addEventListener('resize', syncViewport))
onUnmounted(() => window.removeEventListener('resize', syncViewport))
</script>

<style scoped lang="scss">
.system-layout { height: 100%; min-width: 0; }
.system-content { min-width: 0; }
.system-sidebar {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--chrome-sidebar-bg);
  border-right: 1px solid var(--chrome-sidebar-border);
  transition: width var(--motion-base) ease;
}
.system-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 72px;
  padding: 0 14px;
  overflow: hidden;
  white-space: nowrap;
  border-bottom: 1px solid var(--chrome-sidebar-border);
}
.system-seal {
  display: inline-flex;
  flex: 0 0 36px;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid color-mix(in srgb, var(--brand-vermilion) 72%, transparent);
  border-radius: 11px 11px 11px 3px;
  background: color-mix(in srgb, var(--brand-vermilion) 18%, transparent);
  color: var(--el-color-white);
  font-family: var(--font-data);
  font-size: 13px;
  font-weight: 800;
  letter-spacing: .08em;
}
.system-brand__copy { display: flex; flex-direction: column; color: var(--el-color-white); }
.system-brand__copy strong { font-size: 15px; font-weight: 750; letter-spacing: .04em; }
.system-brand__copy small { margin-top: 4px; color: var(--chrome-menu-text); font-family: var(--font-data); font-size: 8px; letter-spacing: .1em; }
:deep(.el-menu) { flex: 1; padding: 14px 10px; overflow-x: hidden; border-right: none; }
.collapsed :deep(.el-menu) { padding: 8px 4px; }
.collapsed :deep(.el-menu--collapse) { width: 56px; }
:deep(.el-menu-item) { height: 44px; margin-bottom: 5px; border-radius: var(--radius-sm); font-weight: 620; transition: background-color var(--motion-base) ease; }
:deep(.el-menu-item:hover) { background: var(--chrome-menu-hover-bg) !important; color: var(--chrome-menu-hover-text) !important; }
:deep(.el-menu-item.is-active) { background: var(--chrome-menu-active-bg) !important; box-shadow: inset 3px 0 0 var(--chrome-menu-active-bar), var(--chrome-menu-active-glow); }
.collapse-bar { display: flex; align-items: center; justify-content: center; gap: 6px; height: 52px; border: 0; border-top: 1px solid var(--chrome-sidebar-border); background: transparent; color: var(--chrome-menu-text); cursor: pointer; font-size: 13px; }
.collapse-bar:hover { background: var(--chrome-menu-hover-bg); color: var(--chrome-menu-hover-text); }
.collapse-bar:focus-visible { outline: none; box-shadow: var(--focus-ring); }
@media (prefers-reduced-motion: reduce) { .system-sidebar, :deep(.el-menu-item) { transition: none; } }
</style>
