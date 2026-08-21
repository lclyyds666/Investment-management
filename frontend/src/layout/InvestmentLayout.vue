<template>
  <el-container class="investment-layout">
    <el-aside v-if="!compact" :width="collapsed ? '68px' : '224px'" class="legal-sidebar">
      <BrandBlock :collapsed="collapsed" />
      <LegalMenu :collapsed="collapsed" :active="activeMenu" :items="menus" :alert-count="alertStore.count" />
      <button class="collapse-control" type="button" :aria-label="collapsed ? '展开导航' : '收起导航'" @click="collapsed = !collapsed">
        <el-icon><component :is="collapsed ? 'Expand' : 'Fold'" /></el-icon>
        <span v-if="!collapsed">收起导航</span>
      </button>
    </el-aside>

    <el-drawer v-model="drawerVisible" direction="ltr" size="248px" :with-header="false" class="legal-nav-drawer">
      <BrandBlock />
      <LegalMenu :active="activeMenu" :items="menus" :alert-count="alertStore.count" @select="drawerVisible = false" />
    </el-drawer>

    <el-container class="investment-workspace" direction="vertical">
      <div class="header-wrap">
        <el-button v-if="compact" class="menu-trigger" :icon="Menu" circle aria-label="打开导航" @click="drawerVisible = true" />
        <GlobalHeader context-label="山东出版投资有限公司 · 法务风控" show-assistant-action />
      </div>
      <el-main class="legal-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElIcon, ElMenu, ElMenuItem, ElNotification } from 'element-plus'
import { Bell, Briefcase, DataBoard, DocumentChecked, Menu, TrendCharts, UserFilled } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import GlobalHeader from '@/components/GlobalHeader.vue'
import { useLegalAlertsStore } from '@/store/legalAlerts'
import { usePortalStore } from '@/store/portal'
import { RESOURCE_CODES } from '@/constants/business'
import { alertTypeLabel } from '@/constants/legalRisk'

const BrandBlock = defineComponent({
  props: { collapsed: Boolean },
  setup(props) {
    return () => h('div', { class: ['legal-brand', { 'is-collapsed': props.collapsed }] }, [
      h('span', { class: 'legal-brand__seal' }, '法'),
      props.collapsed ? null : h('span', { class: 'legal-brand__text' }, [
        h('strong', '法务风控'),
        h('small', 'LEGAL RISK CONTROL')
      ])
    ])
  }
})

const LegalMenu = defineComponent({
  props: { collapsed: Boolean, active: String, items: Array, alertCount: Number },
  emits: ['select'],
  setup(props, { emit }) {
    const router = useRouter()
    return () => h(ElMenu, {
      defaultActive: props.active,
      collapse: props.collapsed,
      collapseTransition: false,
      class: 'legal-menu',
      onSelect: (path) => { router.push(path); emit('select') }
    }, () => (props.items || []).map((item) => h(ElMenuItem, { index: item.path, key: item.path }, () => [
      h(ElIcon, null, () => h(item.icon)),
      h('span', { class: 'legal-menu__label' }, item.label),
      item.badge && props.alertCount ? h('span', { class: 'legal-menu__badge' }, props.alertCount > 99 ? '99+' : props.alertCount) : null
    ])))
  }
})

const route = useRoute()
const router = useRouter()
const portalStore = usePortalStore()
const alertStore = useLegalAlertsStore()
const compact = ref(window.innerWidth <= 860)
const collapsed = ref(false)
const drawerVisible = ref(false)
const activeMenu = computed(() => {
  if (route.path.includes('/cases')) return '/investment/legal-risk/cases'
  return route.path
})

const allMenus = [
  { path: '/investment/legal-risk/dashboard', label: '法务工作台', icon: DataBoard, resource: RESOURCE_CODES.INVEST_LEGAL_DASHBOARD },
  { path: '/investment/legal-risk/cases', label: '案件管理', icon: Briefcase, resource: RESOURCE_CODES.INVEST_LEGAL_CASES },
  { path: '/investment/legal-risk/contracts', label: '合同管理', icon: DocumentChecked, resource: RESOURCE_CODES.INVEST_LEGAL_CONTRACTS },
  { path: '/investment/legal-risk/alerts', label: '预警任务', icon: Bell, resource: RESOURCE_CODES.INVEST_LEGAL_ALERTS, badge: true },
  { path: '/investment/legal-risk/statistics', label: '统计分析', icon: TrendCharts, resource: RESOURCE_CODES.INVEST_LEGAL_STATISTICS },
  { path: '/investment/legal-risk/users', label: '通知人员', icon: UserFilled, resource: RESOURCE_CODES.INVEST_LEGAL_ADMIN }
]
const menus = computed(() => allMenus.filter((item) => (
  !item.resource || portalStore.hasResource(item.resource)
)))

const syncViewport = () => {
  compact.value = window.innerWidth <= 860
  if (!compact.value) drawerVisible.value = false
}

watch(() => alertStore.importantAlerts, (alerts) => {
  if (!alerts?.length) return
  const seen = new Set(JSON.parse(localStorage.getItem('legalCriticalAlertSeen') || '[]'))
  const alert = alerts.find((item) => !seen.has(item.id))
  if (!alert) return
  seen.add(alert.id)
  localStorage.setItem('legalCriticalAlertSeen', JSON.stringify([...seen].slice(-100)))
  ElNotification({
    title: '重要法务预警',
    message: `${alertTypeLabel(alert.alert_type)}，到期日 ${alert.due_date}`,
    type: 'warning',
    duration: 8000,
    onClick: () => router.push({ path: '/investment/legal-risk/alerts', query: { status: 'pending' } })
  })
}, { deep: true })

onMounted(() => {
  alertStore.startPolling()
  window.addEventListener('resize', syncViewport)
})
onUnmounted(() => {
  alertStore.stopPolling()
  window.removeEventListener('resize', syncViewport)
})
</script>

<style scoped lang="scss">
.investment-layout {
  width: 100%;
  height: 100%;
  min-width: 0;
  background: var(--app-bg);
}

.legal-sidebar {
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid var(--chrome-sidebar-border);
  background: var(--chrome-sidebar-bg);
  transition: width 180ms ease;
}

:deep(.legal-brand) {
  display: flex;
  align-items: center;
  height: 72px;
  min-width: 0;
  padding: 0 16px;
  border-bottom: 1px solid var(--chrome-sidebar-border);
}

:deep(.legal-brand.is-collapsed) { justify-content: center; padding-inline: 8px; }
:deep(.legal-brand__seal) {
  display: grid;
  flex: 0 0 38px;
  width: 38px;
  height: 38px;
  place-items: center;
  border: 1px solid color-mix(in srgb, var(--brand-vermilion) 45%, transparent);
  border-radius: 4px;
  color: #fff;
  background: var(--brand-vermilion);
  font-family: var(--font-display);
  font-size: 21px;
  font-weight: 800;
}

:deep(.legal-brand__text) { display: flex; min-width: 0; margin-left: 12px; flex-direction: column; }
:deep(.legal-brand__text strong) { color: var(--chrome-title-color); font-size: 16px; letter-spacing: 0; }
:deep(.legal-brand__text small) { margin-top: 3px; color: var(--el-text-color-secondary); font-family: var(--font-data); font-size: 9px; letter-spacing: 0; }

:deep(.legal-menu) { flex: 1; padding: 14px 8px; border-right: 0; background: transparent; }
:deep(.legal-menu .el-menu-item) { height: 46px; margin-bottom: 4px; border-radius: 5px; color: var(--chrome-menu-text); }
:deep(.legal-menu .el-menu-item.is-active) { color: var(--chrome-menu-active-text); background: var(--chrome-menu-active-bg); }
:deep(.legal-menu__label) { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
:deep(.legal-menu__badge) {
  min-width: 22px;
  height: 20px;
  margin-left: auto;
  padding: 0 6px;
  border-radius: 10px;
  color: #fff;
  background: var(--brand-vermilion);
  font-family: var(--font-data);
  font-size: 11px;
  line-height: 20px;
  text-align: center;
}

.collapse-control {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 100%;
  height: 48px;
  border: 0;
  border-top: 1px solid var(--chrome-sidebar-border);
  color: var(--chrome-menu-text);
  background: transparent;
  cursor: pointer;
}

.investment-workspace { min-width: 0; height: 100%; }
.header-wrap { position: relative; display: flex; flex: 0 0 72px; min-width: 0; }
.header-wrap :deep(.global-header) { flex: 1; }
.menu-trigger { position: absolute; z-index: 20; top: 18px; left: 12px; }
.header-wrap:has(.menu-trigger) :deep(.global-header) { padding-left: 60px; }
.legal-main { min-height: 0; overflow-y: auto; }

@media (max-width: 860px) {
  .legal-main { padding: 14px; }
}
</style>
