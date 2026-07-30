<template>
  <el-container class="app-wrapper">
    <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar" :class="{ collapsed }">
      <div class="logo" aria-label="山东出版供应链平台">
        <span class="logo-seal">SD</span>
        <span v-show="!collapsed" class="logo-wordmark">
          <strong>出版供应链平台</strong>
          <small>SUPPLY CHAIN OPERATIONS</small>
        </span>
      </div>
      <el-menu
        :default-active="activeMenu"
        :collapse="collapsed"
        :collapse-transition="false"
        router
        background-color="transparent"
        text-color="var(--chrome-menu-text)"
        active-text-color="var(--chrome-menu-active-text)"
      >
        <template v-for="item in menus" :key="item.group || item.path">
          <!-- 分组一级菜单（如「经营合规」）→ 折叠子菜单；标题角标=组内子项待审批合计 -->
          <el-sub-menu v-if="item.group" :index="item.group">
            <template #title>
              <el-icon><component :is="item.icon" /></el-icon>
              <span class="menu-label">{{ item.group }}</span>
              <span v-if="groupBadge(item)" class="nav-badge">{{ badgeText(groupBadge(item)) }}</span>
            </template>
            <el-menu-item v-for="sub in item.children" :key="sub.path" :index="sub.path">
              <el-icon><component :is="sub.meta.icon" /></el-icon>
              <span class="menu-label">{{ sub.meta.title }}</span>
              <span v-if="menuBadge(sub.path)" class="nav-badge">{{ badgeText(menuBadge(sub.path)) }}</span>
            </el-menu-item>
          </el-sub-menu>
          <!-- 普通一级菜单 -->
          <el-menu-item v-else :index="item.path">
            <el-icon><component :is="item.meta.icon" /></el-icon>
            <span class="menu-label">{{ item.meta.title }}</span>
            <span v-if="menuBadge(item.path)" class="nav-badge">{{ badgeText(menuBadge(item.path)) }}</span>
          </el-menu-item>
        </template>
      </el-menu>

      <!-- 收起/展开 -->
      <div class="collapse-bar" @click="toggleCollapse">
        <el-icon><component :is="collapsed ? 'Expand' : 'Fold'" /></el-icon>
        <span v-show="!collapsed">收起菜单</span>
      </div>
    </el-aside>

    <el-container>
      <el-header class="header">
        <div class="title-block">
          <span class="title">山东出版供应链管理有限公司</span>
          <span class="title-subtitle">业务协同与经营决策工作台</span>
        </div>
        <div class="header-right">
          <ThemeToggle />
          <UserDropdown />
        </div>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { useApprovalBadgeStore } from '@/store/approvalBadge'
import { ROLES, LEGAL_COUNSEL_PATHS } from '@/constants/business'
import UserDropdown from '@/components/UserDropdown.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const badgeStore = useApprovalBadgeStore()

const activeMenu = computed(() => route.path)

// 导航角标：按当前角色的待我审批数量。/contract=合同类、/approval=业务审批类
function menuBadge(path) {
  if (path === '/contract') return badgeStore.contract
  if (path === '/approval') return badgeStore.business
  return 0
}
// 分组标题角标 = 组内各子项角标之和
function groupBadge(item) {
  return (item.children || []).reduce((acc, sub) => acc + menuBadge(sub.path), 0)
}
// 角标文案：超过 99 显示 99+
function badgeText(n) {
  return n > 99 ? '99+' : String(n)
}

// 登录期间轮询待审批数量（30s）；组件卸载（登出跳登录页）时停止
onMounted(() => badgeStore.startPolling())
onUnmounted(() => badgeStore.stopPolling())

// 侧边栏收起/展开（localStorage 持久化）
const collapsed = ref(localStorage.getItem('sidebar_collapsed') === '1')
function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem('sidebar_collapsed', collapsed.value ? '1' : '0')
}

// 从路由表生成菜单：按角色 / 超管过滤，再按 meta.group 归组为折叠子菜单
const menus = computed(() => {
  const root = router.options.routes.find((r) => r.path === '/')
  const isLegalCounsel = !userStore.isSuperuser && userStore.role === ROLES.LEGAL_COUNSEL
  const visible = (root?.children || [])
    .filter((c) => c.meta?.title)
    // 按 meta.roles 控制各角色可见菜单（无 roles = 全部可见；hasRole 对超管恒 true）
    .filter((c) => userStore.hasRole(c.meta.roles))
    // 系统管理（用户管理/操作日志）仅超管可见
    .filter((c) => !c.meta.requiresSuperuser || userStore.isSuperuser)
    // 法律顾问仅保留其允许入口（合同管理 / 客户档案库 / 个人设置）
    .filter((c) => !isLegalCounsel || LEGAL_COUNSEL_PATHS.includes('/' + c.path))

  const result = []
  const groups = {}
  for (const c of visible) {
    const item = { path: '/' + c.path, meta: c.meta }
    if (c.meta.group) {
      let g = groups[c.meta.group]
      if (!g) {
        g = { group: c.meta.group, icon: c.meta.groupIcon || 'Menu', children: [] }
        groups[c.meta.group] = g
        result.push(g)
      }
      g.children.push(item)
    } else {
      result.push(item)
    }
  }
  return result
})
</script>

<style scoped lang="scss">
.app-wrapper {
  height: 100%;
  min-width: 0;
}
.sidebar {
  background: var(--chrome-sidebar-bg);
  position: relative;
  border-right: 1px solid var(--chrome-sidebar-border);
  transition: all var(--motion-base) ease;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  .logo {
    height: 72px;
    padding: 0 14px;
    display: flex;
    align-items: center;
    gap: 10px;
    white-space: nowrap;
    overflow: hidden;
    border-bottom: 1px solid var(--chrome-sidebar-border);
  }
  .logo-seal {
    width: 36px;
    height: 36px;
    flex: 0 0 36px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid color-mix(in srgb, var(--brand-vermilion) 72%, transparent);
    border-radius: 11px 11px 11px 3px;
    color: var(--el-color-white);
    background: color-mix(in srgb, var(--brand-vermilion) 18%, transparent);
    font-family: var(--font-data);
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 0.08em;
  }
  .logo-wordmark {
    min-width: 0;
    display: flex;
    flex-direction: column;
    color: var(--el-color-white);
    line-height: 1.25;
    strong { font-size: 15px; font-weight: 750; letter-spacing: 0.04em; }
    small { margin-top: 4px; color: var(--chrome-menu-text); font-family: var(--font-data); font-size: 8px; letter-spacing: 0.1em; }
  }
  /* 菜单区占满、可滚动；收起条固定底部 */
  :deep(.el-menu) {
    flex: 1;
    border-right: none;
    padding: 14px 10px;
    overflow-x: hidden;
  }
  /* 收起态：菜单不再受 220px 约束，图标居中 */
  &.collapsed :deep(.el-menu) {
    padding: 8px 4px;
  }
  &.collapsed :deep(.el-menu--collapse) {
    width: 56px;
  }
  /* 收起条 */
  .collapse-bar {
    height: 52px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    cursor: pointer;
    color: var(--chrome-menu-text);
    border-top: 1px solid var(--chrome-sidebar-border);
    font-size: 13px;
    transition: all var(--motion-base) ease;
    &:hover {
      background: var(--chrome-menu-hover-bg);
      color: var(--chrome-menu-hover-text);
    }
  }
  :deep(.el-menu-item) {
    height: 44px;
    border-radius: var(--radius-sm);
    margin-bottom: 5px;
    font-weight: 620;
    transition: all var(--motion-base) ease;
  }
  /* 菜单标题文字占满剩余宽度，把角标推到行尾并与文字同基线 */
  .menu-label { flex: 1; }
  /* 导航待审批角标：内联小药丸，垂直居中对齐导航文字（不再浮在右上角） */
  .nav-badge {
    flex-shrink: 0;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 18px;
    height: 18px;
    padding: 0 5px;
    margin-left: 8px;
    border-radius: 9px;
    background: var(--el-color-danger);
    color: var(--el-color-white);
    font-size: 12px;
    line-height: 1;
    font-weight: 600;
    vertical-align: middle;
  }
  /* 收起态：文字隐藏，角标一并隐藏，避免溢出图标 */
  &.collapsed .nav-badge { display: none; }
  :deep(.el-menu-item:hover) {
    background: var(--chrome-menu-hover-bg) !important;
    color: var(--chrome-menu-hover-text) !important;
  }
  :deep(.el-menu-item.is-active) {
    background: var(--chrome-menu-active-bg) !important;
    box-shadow: inset 3px 0 0 var(--chrome-menu-active-bar), var(--chrome-menu-active-glow);
  }
  /* 折叠子菜单：一级标题沿用外壳风格 */
  :deep(.el-sub-menu__title) {
    height: 44px;
    border-radius: var(--radius-sm);
    margin-bottom: 5px;
    font-weight: 620;
    transition: all var(--motion-base) ease;
  }
  :deep(.el-sub-menu__title:hover) {
    background: var(--chrome-menu-hover-bg) !important;
    color: var(--chrome-menu-hover-text) !important;
  }
  /* 含选中子项时，父级标题点亮 */
  :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
    color: var(--chrome-menu-active-text) !important;
  }
  /* 展开的子项容器保持透明背景 + 子项缩进 */
  :deep(.el-menu--inline) {
    background: transparent !important;
  }
  :deep(.el-menu--inline .el-menu-item) {
    padding-left: 44px !important;
    min-width: auto;
  }
}
.header {
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 clamp(18px, 1.7vw, 30px);
  background: var(--chrome-header-bg);
  border-bottom: 1px solid var(--chrome-header-border);
  box-shadow: var(--chrome-header-shadow);
  backdrop-filter: blur(16px);
  transition: all var(--motion-base) ease;
  .title-block {
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .title {
    overflow: hidden;
    color: var(--chrome-title-color);
    font-family: var(--font-display);
    font-size: 17px;
    font-weight: 750;
    letter-spacing: 0.04em;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .title-subtitle {
    margin-top: 3px;
    color: var(--el-text-color-secondary);
    font-size: 11px;
    letter-spacing: 0.08em;
  }
  .user {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    outline: none;
    color: var(--chrome-title-color);
  }
  .header-right {
    display: flex;
    align-items: center;
    gap: 12px;
  }
}

@media (max-width: 1100px) {
  .header .title-subtitle { display: none; }
}

@media (max-width: 760px) {
  .header .title { font-size: 14px; }
  .header .header-right { gap: 6px; }
}
</style>
