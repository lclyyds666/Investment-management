<template>
  <el-container class="app-wrapper">
    <el-aside :width="collapsed ? '64px' : '220px'" class="sidebar" :class="{ collapsed }">
      <div class="logo">{{ collapsed ? '供链' : '出版供应链平台' }}</div>
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
        <span class="title">山东出版供应链管理公司业务平台</span>
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
    // 除法律顾问外，导航展示全部菜单项（仅可见）：用户管理/操作日志等敏感页的实际访问
    // 仍由路由守卫 permission.js 按 requiresSuperuser/roles 拦截，操作权限不变。
    // 法律顾问仍只保留其允许入口（合同管理/审批中心/个人设置）。
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
}
/* 侧边栏(外壳变量驱动:明亮=白底、暗黑=科技霓虹) */
.sidebar {
  background: var(--chrome-sidebar-bg);
  position: relative;
  border-right: 1px solid var(--chrome-sidebar-border);
  /* 收起/展开平滑过渡 + 主题切换过渡 */
  transition: width 0.28s ease, background-color 0.3s ease, border-color 0.3s ease;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  .logo {
    height: 60px;
    line-height: 60px;
    text-align: center;
    font-size: 16px;
    font-weight: 800;
    letter-spacing: 1px;
    white-space: nowrap;
    overflow: hidden;
    background: var(--chrome-logo-gradient);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    text-shadow: var(--chrome-logo-shadow);
    border-bottom: 1px solid var(--chrome-sidebar-border);
  }
  /* 菜单区占满、可滚动；收起条固定底部 */
  :deep(.el-menu) {
    flex: 1;
    border-right: none;
    padding: 8px;
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
    height: 46px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    cursor: pointer;
    color: var(--chrome-menu-text);
    border-top: 1px solid var(--chrome-sidebar-border);
    transition: background 0.2s, color 0.2s;
    &:hover {
      background: var(--chrome-menu-hover-bg);
      color: var(--chrome-menu-hover-text);
    }
  }
  :deep(.el-menu-item) {
    height: 46px;
    border-radius: 8px;
    margin-bottom: 4px;
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
    color: #fff;
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
    height: 46px;
    border-radius: 8px;
    margin-bottom: 4px;
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
/* 顶栏(外壳变量驱动) */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--chrome-header-bg);
  border-bottom: 1px solid var(--chrome-header-border);
  box-shadow: var(--chrome-header-shadow);
  transition: background-color 0.3s ease, border-color 0.3s ease;
  .title {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 1px;
    background: var(--chrome-title-gradient);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
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
</style>
