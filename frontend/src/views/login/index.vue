<template>
  <div class="login-page">
    <!-- 科技动态背景 -->
    <div class="bg-grid"></div>
    <div class="bg-orb orb1"></div>
    <div class="bg-orb orb2"></div>

    <el-card class="login-card">
      <div class="brand">
        <div class="brand-logo">SD·SCM</div>
        <h2>山东出版供应链管理公司</h2>
        <p>业务平台 · 数据智能中心</p>
      </div>
      <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="onSubmit">
        <el-form-item prop="username">
          <el-input v-model="form.username" placeholder="账号" :prefix-icon="User" size="large" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            :prefix-icon="Lock"
            size="large"
            show-password
            @keyup.enter="onSubmit"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" :loading="loading" class="login-btn" @click="onSubmit">
            登 录
          </el-button>
        </el-form-item>
      </el-form>
      <div class="tips">
        演示账号（密码均 123456）：op 业务经办 / review 业务复核 / risk 风控 /
        fin 财务经办 / finr 财务复核 / scm 供管负责人 / inv 投资负责人 / admin 超管
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

async function onSubmit() {
  await formRef.value?.validate()
  loading.value = true
  try {
    await userStore.login(form.username, form.password)
    ElMessage.success('登录成功')
    const redirect = route.query.redirect || '/'
    router.replace(redirect)
  } catch (e) {
    // 错误信息已由拦截器统一提示
  } finally {
    loading.value = false
  }
}
</script>

<style scoped lang="scss">
.login-page {
  height: 100%;
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(1000px 600px at 20% 10%, rgba(28, 155, 230, 0.25), transparent 60%),
    radial-gradient(900px 500px at 85% 90%, rgba(34, 211, 238, 0.2), transparent 60%),
    #030b1f;
}
/* 动态网格 */
.bg-grid {
  position: absolute;
  inset: -50%;
  background-image:
    linear-gradient(rgba(34, 211, 238, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(34, 211, 238, 0.08) 1px, transparent 1px);
  background-size: 44px 44px;
  transform: perspective(400px) rotateX(60deg);
  animation: gridmove 18s linear infinite;
}
@keyframes gridmove { from { background-position: 0 0; } to { background-position: 0 440px; } }
/* 光晕 */
.bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(60px);
  opacity: 0.5;
  animation: float 12s ease-in-out infinite;
}
.orb1 { width: 340px; height: 340px; background: #1c9be6; top: 8%; left: 10%; }
.orb2 { width: 300px; height: 300px; background: #22d3ee; bottom: 6%; right: 12%; animation-delay: -6s; }
@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-26px); } }

/* 玻璃霓虹登录卡 */
.login-card {
  position: relative;
  z-index: 2;
  width: 400px;
  padding: 14px 22px;
  background: rgba(10, 28, 60, 0.55) !important;
  backdrop-filter: blur(14px);
  border: 1px solid rgba(34, 211, 238, 0.35) !important;
  box-shadow: 0 0 40px rgba(28, 155, 230, 0.3), inset 0 0 30px rgba(28, 155, 230, 0.06) !important;
}
.login-card::before { background: linear-gradient(90deg, #22d3ee, #1c9be6) !important; }
.brand {
  text-align: center;
  margin-bottom: 22px;
  .brand-logo {
    display: inline-block;
    font-weight: 900;
    letter-spacing: 2px;
    font-size: 20px;
    padding: 6px 14px;
    border-radius: 8px;
    background: linear-gradient(135deg, #1c9be6, #22d3ee);
    color: #021018;
    box-shadow: 0 0 20px rgba(34, 211, 238, 0.5);
    margin-bottom: 12px;
  }
  h2 {
    margin: 0;
    font-size: 20px;
    background: linear-gradient(90deg, #eafcff, #7fd8ff);
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }
  p { margin: 6px 0 0; color: #6f9dcf; font-size: 13px; letter-spacing: 1px; }
}
.login-btn {
  width: 100%;
  letter-spacing: 6px;
  font-weight: 700;
}
.tips {
  text-align: center;
  font-size: 12px;
  color: #5b82b3;
  line-height: 1.7;
}
:deep(.el-input__wrapper) {
  background: rgba(6, 20, 46, 0.6);
  box-shadow: 0 0 0 1px rgba(34, 211, 238, 0.25) inset;
}
:deep(.el-input__inner) { color: #d7ecff; }
:deep(.el-input__inner::placeholder) { color: #5b82b3; }
</style>
