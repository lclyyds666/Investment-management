<template>
  <span>
    <el-dropdown @command="onCommand">
      <span class="user">
        {{ userStore.userInfo?.full_name || '用户' }}
        <el-tag size="small" type="warning" effect="plain">{{ roleLabel }}</el-tag>
        <el-icon><ArrowDown /></el-icon>
      </span>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="info" :icon="User">个人信息</el-dropdown-item>
          <el-dropdown-item command="password" :icon="Lock">修改密码</el-dropdown-item>
          <el-dropdown-item command="username" :icon="EditPen">修改用户名</el-dropdown-item>
          <el-dropdown-item command="signature" :icon="Stamp">电子签章</el-dropdown-item>
          <el-dropdown-item command="logout" :icon="SwitchButton" divided>退出登录</el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>

    <!-- 个人信息 -->
    <el-dialog v-model="infoVisible" title="个人信息" width="440px">
      <el-descriptions :column="1" border>
        <el-descriptions-item label="姓名">{{ info?.full_name || '—' }}</el-descriptions-item>
        <el-descriptions-item label="登录账号">{{ info?.username || '—' }}</el-descriptions-item>
        <el-descriptions-item label="角色">
          <el-tag type="warning" size="small">{{ info?.role_label || roleLabel }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="所属部门">{{ info?.department || '—' }}</el-descriptions-item>
        <el-descriptions-item label="超级管理员">
          <el-tag :type="info?.is_superuser ? 'success' : 'info'" size="small">
            {{ info?.is_superuser ? '是' : '否' }}
          </el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer><el-button @click="infoVisible = false">关闭</el-button></template>
    </el-dialog>

    <!-- 修改密码 -->
    <el-dialog v-model="pwdVisible" title="修改密码" width="460px" @closed="resetPwd">
      <el-form ref="pwdRef" :model="pwd" :rules="pwdRules" label-width="100px" class="dlg-form">
        <el-form-item label="原密码" prop="old_password">
          <el-input v-model="pwd.old_password" type="password" show-password autocomplete="off" />
        </el-form-item>
        <el-form-item label="新密码" prop="new_password">
          <el-input v-model="pwd.new_password" type="password" show-password autocomplete="off" />
        </el-form-item>
        <el-form-item label="确认新密码" prop="confirm">
          <el-input v-model="pwd.confirm" type="password" show-password autocomplete="off" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="pwdSaving" @click="onChangePassword">保存</el-button>
      </template>
    </el-dialog>

    <!-- 修改用户名 -->
    <el-dialog v-model="acctVisible" title="修改用户名" width="460px" @closed="resetAcct">
      <el-alert
        type="info" :closable="false" show-icon class="mb"
        title="修改登录账号后无需重新登录（令牌以用户 ID 为主体）。"
      />
      <el-form ref="acctRef" :model="acct" :rules="acctRules" label-width="100px" class="dlg-form">
        <el-form-item label="新登录账号" prop="new_username">
          <el-input v-model="acct.new_username" placeholder="字母 / 数字 / 下划线，3-64 位" />
        </el-form-item>
        <el-form-item label="当前密码" prop="password">
          <el-input v-model="acct.password" type="password" show-password autocomplete="off" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="acctVisible = false">取消</el-button>
        <el-button type="primary" :loading="acctSaving" @click="onChangeUsername">保存</el-button>
      </template>
    </el-dialog>

    <!-- 电子签章 -->
    <el-dialog v-model="sigVisible" title="电子签章" width="520px" @closed="resetSig">
      <el-alert
        v-if="signatureDisabled"
        type="warning" :closable="false" show-icon
        title="「信息维护」角色无电子签名权限"
        description="该角色仅承担信息维护职责、不参与审批签章，故不提供电子签名的上传与维护功能。"
      />
      <template v-else>
        <el-alert
          type="info" :closable="false" show-icon class="mb"
          title="签名将作为您的核心签章资产，审批通过时自动附加到审批单对应环节。"
        />
        <div class="sig-preview">
          <div class="sig-label">当前签名</div>
          <div class="sig-box">
            <img v-if="preview" :src="preview" alt="签名" class="sig-img" />
            <el-empty v-else :image-size="50" description="暂无签名" />
          </div>
        </div>
        <el-upload
          class="sig-upload" drag action="#" accept="image/*"
          :auto-upload="false" :show-file-list="false" :on-change="onFileChange"
        >
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">点击或拖拽<em>上传签名图片</em>（PNG/JPG，建议透明底）</div>
        </el-upload>
      </template>
      <template #footer>
        <el-button @click="sigVisible = false">关闭</el-button>
        <template v-if="!signatureDisabled">
          <el-button @click="resetSigPreview">重置</el-button>
          <el-button type="primary" :loading="sigSaving" :disabled="preview === (info?.signature || '')" @click="saveSig">
            保存签名
          </el-button>
        </template>
      </template>
    </el-dialog>
  </span>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown, User, Lock, EditPen, Stamp, SwitchButton, UploadFilled } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { roleLabel as toRoleLabel, ROLES } from '@/constants/business'
import { getMe, updateSignature, changeMyPassword, changeMyUsername } from '@/api/user'
import { logout as logoutAudit } from '@/api/audit'

const router = useRouter()
const userStore = useUserStore()
const roleLabel = computed(() => userStore.roleLabel || toRoleLabel(userStore.role))
const signatureDisabled = computed(() => userStore.role === ROLES.INFO_MAINTAINER)

const info = ref(userStore.userInfo)

// 弹窗可见性
const infoVisible = ref(false)
const pwdVisible = ref(false)
const acctVisible = ref(false)
const sigVisible = ref(false)

async function refreshInfo() {
  try {
    info.value = await getMe()
    userStore.setUserInfo(info.value)
  } catch { /* 保底用 store 里的信息 */ }
}

async function onCommand(cmd) {
  if (cmd === 'logout') {
    // 先留痕退出（best-effort，令牌还在时调用），再清本地并跳登录
    await logoutAudit()
    userStore.logout()
    router.replace('/login')
    return
  }
  if (cmd === 'info') { refreshInfo(); infoVisible.value = true }
  else if (cmd === 'password') { pwdVisible.value = true }
  else if (cmd === 'username') { acctVisible.value = true }
  else if (cmd === 'signature') {
    preview.value = info.value?.signature || ''
    if (!info.value) refreshInfo()
    sigVisible.value = true
  }
}

// —— 修改密码 ——
const pwdRef = ref()
const pwdSaving = ref(false)
const pwd = reactive({ old_password: '', new_password: '', confirm: '' })
const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: 'blur' }],
  new_password: [{ required: true, min: 6, message: '新密码至少 6 位', trigger: 'blur' }],
  confirm: [
    { required: true, message: '请再次输入新密码', trigger: 'blur' },
    {
      validator: (_r, v, cb) => (v === pwd.new_password ? cb() : cb(new Error('两次输入的密码不一致'))),
      trigger: 'blur'
    }
  ]
}
async function onChangePassword() {
  await pwdRef.value?.validate()
  pwdSaving.value = true
  try {
    await changeMyPassword(pwd.old_password, pwd.new_password)
    ElMessage.success('密码修改成功，请牢记新密码')
    pwdVisible.value = false
  } finally {
    pwdSaving.value = false
  }
}
function resetPwd() {
  pwd.old_password = pwd.new_password = pwd.confirm = ''
  pwdRef.value?.clearValidate?.()
}

// —— 修改用户名 ——
const acctRef = ref()
const acctSaving = ref(false)
const acct = reactive({ new_username: '', password: '' })
const acctRules = {
  new_username: [
    { required: true, message: '请输入新登录账号', trigger: 'blur' },
    { min: 3, max: 64, message: '长度 3-64 位', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_]+$/, message: '仅允许字母、数字、下划线', trigger: 'blur' }
  ],
  password: [{ required: true, message: '请输入当前密码', trigger: 'blur' }]
}
async function onChangeUsername() {
  await acctRef.value?.validate()
  acctSaving.value = true
  try {
    const res = await changeMyUsername(acct.new_username, acct.password)
    ElMessage.success('登录账号已更新')
    info.value = res
    userStore.setUserInfo(res)
    acctVisible.value = false
  } finally {
    acctSaving.value = false
  }
}
function resetAcct() {
  acct.new_username = acct.password = ''
  acctRef.value?.clearValidate?.()
}

// —— 电子签章 ——
const sigSaving = ref(false)
const preview = ref(userStore.userInfo?.signature || '')
function onFileChange(file) {
  const raw = file.raw
  if (!raw) return
  if (!raw.type.startsWith('image/')) {
    ElMessage.error('请选择图片文件')
    return
  }
  const reader = new FileReader()
  reader.onload = (e) => {
    preview.value = e.target.result
    ElMessage.success('已载入签名图片，点击"保存签名"生效')
  }
  reader.readAsDataURL(raw)
}
function resetSigPreview() {
  preview.value = info.value?.signature || ''
}
async function saveSig() {
  sigSaving.value = true
  try {
    const res = await updateSignature(preview.value)
    info.value = res
    preview.value = res.signature || ''
    userStore.setUserInfo(res)
    ElMessage.success('签名已保存')
  } finally {
    sigSaving.value = false
  }
}
function resetSig() {
  preview.value = info.value?.signature || ''
}
</script>

<style scoped lang="scss">
.user {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  outline: none;
  color: var(--chrome-title-color);
}
.mb { margin-bottom: 14px; }
/* 弹窗表单：标签固定左侧、不换行，输入框右侧自适应，严禁 Label 换行错位 */
.dlg-form :deep(.el-form-item) {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
}
.dlg-form :deep(.el-form-item__label) {
  white-space: nowrap;
  justify-content: flex-start;
}
.dlg-form :deep(.el-form-item__content) {
  flex: 1;
  min-width: 0;
}
.sig-preview { margin-bottom: 14px; }
.sig-label { color: var(--el-text-color-secondary); font-size: 13px; margin-bottom: 6px; }
.sig-box {
  min-height: 90px;
  border: 1px dashed var(--el-border-color);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
}
.sig-img { max-height: 90px; max-width: 100%; }
.sig-upload { width: 100%; :deep(.el-upload), :deep(.el-upload-dragger) { width: 100%; } }
</style>
