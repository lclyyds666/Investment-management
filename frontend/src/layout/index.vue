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
        text-color="#a9c2e0"
        active-text-color="#22d3ee"
      >
        <template v-for="item in menus" :key="item.group || item.path">
          <!-- 分组一级菜单（如「经营合规管理」）→ 折叠子菜单 -->
          <el-sub-menu v-if="item.group" :index="item.group">
            <template #title>
              <el-icon><component :is="item.icon" /></el-icon>
              <span>{{ item.group }}</span>
            </template>
            <el-menu-item v-for="sub in item.children" :key="sub.path" :index="sub.path">
              <el-icon><component :is="sub.meta.icon" /></el-icon>
              <span>{{ sub.meta.title }}</span>
            </el-menu-item>
          </el-sub-menu>
          <!-- 普通一级菜单 -->
          <el-menu-item v-else :index="item.path">
            <el-icon><component :is="item.meta.icon" /></el-icon>
            <span>{{ item.meta.title }}</span>
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
        <el-dropdown @command="onCommand">
          <span class="user">
            {{ userStore.userInfo?.full_name || '用户' }}
            <el-tag size="small" type="warning" effect="plain">{{ roleLabel }}</el-tag>
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile" :icon="User">个人设置</el-dropdown-item>
              <el-dropdown-item command="logout" :icon="SwitchButton" divided>退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowDown, User, SwitchButton } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { roleLabel as toRoleLabel, ROLES, LEGAL_COUNSEL_PATHS } from '@/constants/business'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const activeMenu = computed(() => route.path)

// 侧边栏收起/展开（localStorage 持久化）
const collapsed = ref(localStorage.getItem('sidebar_collapsed') === '1')
function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem('sidebar_collapsed', collapsed.value ? '1' : '0')
}

// 优先用后端返回的角色中文名，回退到本地映射
const roleLabel = computed(() => userStore.roleLabel || toRoleLabel(userStore.role))

// 从路由表生成菜单：按角色 / 超管过滤，再按 meta.group 归组为折叠子菜单
const menus = computed(() => {
  const root = router.options.routes.find((r) => r.path === '/')
  const isLegalCounsel = !userStore.isSuperuser && userStore.role === ROLES.LEGAL_COUNSEL
  const visible = (root?.children || [])
    .filter((c) => c.meta?.title)
    .filter((c) => userStore.hasRole(c.meta.roles))
    .filter((c) => !c.meta.requiresSuperuser || userStore.isSuperuser)
    // 法律顾问只保留「合同管理 / 审批中心」两个入口
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

function onCommand(cmd) {
  if (cmd === 'logout') {
    userStore.logout()
    router.replace('/login')
  } else if (cmd === 'profile') {
    router.push('/profile')
  }
}
</script>

<style scoped lang="scss">
.app-wrapper {
  height: 100%;
}
/* 深色霓虹侧边栏 */
.sidebar {
  background: linear-gradient(180deg, #0a1b3a 0%, #071228 100%);
  position: relative;
  border-right: 1px solid rgba(34, 211, 238, 0.14);
  /* 收起/展开平滑过渡 */
  transition: width 0.28s ease;
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
    background: linear-gradient(90deg, #39c5ff, #22d3ee);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    text-shadow: 0 0 18px rgba(34, 211, 238, 0.4);
    border-bottom: 1px solid rgba(34, 211, 238, 0.14);
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
    color: #a9c2e0;
    border-top: 1px solid rgba(34, 211, 238, 0.14);
    transition: background 0.2s, color 0.2s;
    &:hover {
      background: rgba(34, 211, 238, 0.08);
      color: #d7f6ff;
    }
  }
  :deep(.el-menu-item) {
    height: 46px;
    border-radius: 8px;
    margin-bottom: 4px;
  }
  :deep(.el-menu-item:hover) {
    background: rgba(34, 211, 238, 0.08) !important;
    color: #d7f6ff !important;
  }
  :deep(.el-menu-item.is-active) {
    background: linear-gradient(90deg, rgba(34, 211, 238, 0.22), rgba(28, 155, 230, 0.05)) !important;
    box-shadow: inset 3px 0 0 #22d3ee, 0 0 16px rgba(34, 211, 238, 0.18);
  }
  /* 折叠子菜单：一级标题沿用霓虹风格 */
  :deep(.el-sub-menu__title) {
    height: 46px;
    border-radius: 8px;
    margin-bottom: 4px;
  }
  :deep(.el-sub-menu__title:hover) {
    background: rgba(34, 211, 238, 0.08) !important;
    color: #d7f6ff !important;
  }
  /* 含选中子项时，父级标题点亮 */
  :deep(.el-sub-menu.is-active > .el-sub-menu__title) {
    color: #22d3ee !important;
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
/* 玻璃质感顶栏 */
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: linear-gradient(90deg, #0a1b3a, #0e2450);
  border-bottom: 1px solid rgba(34, 211, 238, 0.2);
  box-shadow: 0 2px 16px rgba(4, 20, 48, 0.4);
  .title {
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 1px;
    background: linear-gradient(90deg, #eafcff, #7fd8ff);
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
    color: #cfe6ff;
  }
}
</style>
