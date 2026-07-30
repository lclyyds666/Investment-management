<template>
  <div class="login-page">
    <!-- 品牌背景 -->
    <div class="bg-grid"></div>
    <div class="bg-orb orb1"></div>
    <div class="bg-orb orb2"></div>

    <el-card class="login-card">
      <div class="brand">
        <div class="brand-logo">SD·SCM</div>
        <h2>山东出版供应链管理有限公司</h2>
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
    radial-gradient(1000px 600px at 20% 10%, color-mix(in srgb, var(--screen-primary) 18%, transparent), transparent 60%),
    radial-gradient(900px 500px at 85% 90%, color-mix(in srgb, var(--screen-secondary) 15%, transparent), transparent 60%),
    var(--screen-bg);
}
.bg-grid {
  position: absolute;
  inset: -50%;
  background-image:
    linear-gradient(var(--screen-border) 1px, transparent 1px),
    linear-gradient(90deg, var(--screen-border) 1px, transparent 1px);
  background-size: 56px 56px;
  opacity: .42;
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
.orb1 { width: 340px; height: 340px; background: var(--screen-primary); top: 8%; left: 10%; }
.orb2 { width: 300px; height: 300px; background: var(--screen-secondary); bottom: 6%; right: 12%; animation-delay: -6s; }
@keyframes float { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-26px); } }

.login-card {
  position: relative;
  z-index: 2;
  width: min(420px, calc(100vw - 32px));
  padding: 20px 24px;
  background: var(--screen-surface) !important;
  backdrop-filter: blur(18px);
  border: 1px solid var(--screen-border) !important;
  box-shadow: var(--screen-shadow) !important;
}
.login-card::before { background: var(--brand-vermilion) !important; }
.brand {
  text-align: center;
  margin-bottom: 22px;
  .brand-logo {
    display: inline-block;
    font-weight: 900;
    letter-spacing: 2px;
    font-size: 20px;
    padding: 6px 14px;
    border: 1px solid color-mix(in srgb, var(--brand-vermilion) 76%, transparent);
    border-radius: 12px 12px 12px 4px;
    background: color-mix(in srgb, var(--brand-vermilion) 18%, transparent);
    color: var(--screen-text);
    box-shadow: 0 10px 24px color-mix(in srgb, var(--brand-vermilion) 18%, transparent);
    margin-bottom: 12px;
  }
  h2 {
    margin: 0;
    font-size: 20px;
    color: var(--screen-text);
    font-family: var(--font-display);
    letter-spacing: .04em;
  }
  p { margin: 8px 0 0; color: var(--screen-text-muted); font-size: 12px; letter-spacing: .12em; }
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
  border-radius: var(--radius-sm);
  overflow: hidden;
  cursor: pointer;
  flex-shrink: 0;
  border: 1px solid var(--screen-border);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--screen-surface-strong);
  img { width: 100%; height: 100%; display: block; }
  .captcha-loading { color: var(--screen-text-muted); font-size: 12px; }
}
.login-btn {
  width: 100%;
  letter-spacing: 6px;
  font-weight: 700;
}
.tips {
  text-align: center;
  font-size: 12px;
  color: var(--screen-text-muted);
  line-height: 1.7;
}
:deep(.el-input__wrapper) {
  background: var(--screen-surface-strong);
  box-shadow: 0 0 0 1px var(--screen-border) inset;
}
:deep(.el-input__inner) { color: var(--screen-text); }
:deep(.el-input__inner::placeholder) { color: var(--screen-text-muted); }
</style>
