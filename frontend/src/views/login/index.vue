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
        <el-form-item prop="captcha_code">
          <div class="captcha-row">
            <el-input
              v-model="form.captcha_code"
              placeholder="验证码"
              :prefix-icon="Picture"
              size="large"
              maxlength="4"
              @keyup.enter="onSubmit"
            />
            <div class="captcha-img" title="点击刷新验证码" @click="refreshCaptcha">
              <img v-if="captchaImg" :src="captchaImg" alt="验证码" />
              <span v-else class="captcha-loading">加载中…</span>
            </div>
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" :loading="loading" class="login-btn" @click="onSubmit">
            登 录
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, Picture } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { getCaptcha } from '@/api/auth'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const formRef = ref()
const loading = ref(false)
const form = reactive({ username: '', password: '', captcha_code: '' })
const captchaId = ref('')
const captchaImg = ref('')
const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  captcha_code: [{ required: true, message: '请输入验证码', trigger: 'blur' }]
}

async function refreshCaptcha() {
  try {
    const res = await getCaptcha()
    captchaId.value = res.captcha_id
    captchaImg.value = res.image
    form.captcha_code = ''
  } catch (e) {
    // 拦截器已提示
  }
}

async function onSubmit() {
  await formRef.value?.validate()
  loading.value = true
  try {
    await userStore.login(form.username, form.password, captchaId.value, form.captcha_code)
    ElMessage.success('登录成功')
    const redirect = route.query.redirect || '/'
    router.replace(redirect)
  } catch (e) {
    // 错误信息已由拦截器统一提示；无论失败原因都刷新验证码（验证码一次性）
    refreshCaptcha()
  } finally {
    loading.value = false
  }
}

onMounted(refreshCaptcha)
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
    radial-gradient(1000px 600px at 20% 10%, rgba(43, 108, 176, 0.10), transparent 60%),
    radial-gradient(900px 500px at 85% 90%, rgba(43, 108, 176, 0.08), transparent 60%),
    #eef2f7;
}
/* 极淡背景网格 */
.bg-grid {
  position: absolute;
  inset: -50%;
  background-image:
    linear-gradient(rgba(43, 108, 176, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(43, 108, 176, 0.05) 1px, transparent 1px);
  background-size: 44px 44px;
  transform: perspective(400px) rotateX(60deg);
  animation: gridmove 18s linear infinite;
}
@keyframes gridmove { from { background-position: 0 0; } to { background-position: 0 440px; } }
/* 柔和光晕 */
.bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.35;
  animation: float 12s ease-in-out infinite;
}
.orb1 { width: 340px; height: 340px; background: #2b6cb0; top: 8%; left: 10%; }
.orb2 { width: 300px; height: 300px; background: #5b8fc9; bottom: 6%; right: 12%; animation-delay: -6s; }
@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-26px); } }

/* 简洁白色登录卡 */
.login-card {
  position: relative;
  z-index: 2;
  width: 400px;
  padding: 14px 22px;
  background: #fff !important;
  border: 1px solid var(--app-border) !important;
  box-shadow: 0 12px 40px rgba(17, 24, 39, 0.12) !important;
  border-radius: 12px;
}
.brand {
  text-align: center;
  margin-bottom: 22px;
  .brand-logo {
    display: inline-block;
    font-weight: 800;
    letter-spacing: 2px;
    font-size: 20px;
    padding: 6px 14px;
    border-radius: 8px;
    background: var(--el-color-primary);
    color: #fff;
    margin-bottom: 12px;
  }
  h2 {
    margin: 0;
    font-size: 20px;
    color: var(--app-text-1);
  }
  p { margin: 6px 0 0; color: var(--app-text-3); font-size: 13px; letter-spacing: 1px; }
}
.captcha-row {
  display: flex;
  gap: 10px;
  width: 100%;
  .el-input { flex: 1; }
}
.captcha-img {
  width: 120px;
  height: 40px;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  flex-shrink: 0;
  border: 1px solid var(--app-border);
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  img { width: 100%; height: 100%; display: block; }
  .captcha-loading { color: var(--app-text-3); font-size: 12px; }
}
.login-btn {
  width: 100%;
  letter-spacing: 6px;
  font-weight: 700;
}
.tips {
  text-align: center;
  font-size: 12px;
  color: var(--app-text-3);
  line-height: 1.7;
}
</style>
