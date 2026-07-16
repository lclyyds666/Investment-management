import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css' // 暗色主题变量
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'

import App from './App.vue'
import router from './router'
import './permission' // 路由守卫（登录 + 角色拦截）
import './styles/index.scss'

// 主题:后台管理默认浅色专业风;深色科技风仅数据大屏(/screen)启用,
// 由 router 守卫按路由动态挂载/卸载 html.dark(见 router/index.js)。

const app = createApp(App)

// 全局注册 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })

app.mount('#app')
