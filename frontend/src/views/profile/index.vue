<template>
  <div class="profile">
    <el-row :gutter="16">
      <!-- 个人资料 -->
      <el-col :span="10">
        <el-card shadow="never">
          <template #header><span>个人资料</span></template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="姓名">{{ info?.full_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="登录账号">{{ info?.username }}</el-descriptions-item>
            <el-descriptions-item label="角色">
              <el-tag type="warning" size="small">{{ info?.role_label }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="所属部门">{{ info?.department || '—' }}</el-descriptions-item>
            <el-descriptions-item label="超级管理员">
              <el-tag :type="info?.is_superuser ? 'success' : 'info'" size="small">
                {{ info?.is_superuser ? '是' : '否' }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <!-- 纸质签名上传 -->
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <div class="sig-header">
              <span>纸质签名 / 电子签章</span>
              <el-tag :type="hasSig ? 'success' : 'info'" size="small">
                {{ hasSig ? '已设置' : '未设置' }}
              </el-tag>
            </div>
          </template>

          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="签名将作为您的核心签章资产，审批合同通过时自动附加到审批单的对应环节。"
            class="mb"
          />

          <div class="sig-preview">
            <div class="sig-label">当前签名</div>
            <div class="sig-box">
              <img v-if="preview" :src="preview" alt="签名" class="sig-img" />
              <el-empty v-else :image-size="50" description="暂无签名" />
            </div>
          </div>

          <el-upload
            class="sig-upload"
            drag
            action="#"
            accept="image/*"
            :auto-upload="false"
            :show-file-list="false"
            :on-change="onFileChange"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">点击或拖拽<em>上传签名图片</em>（PNG/JPG，建议透明底）</div>
          </el-upload>

          <div class="sig-actions">
            <el-button @click="reset">重置</el-button>
            <el-button type="primary" :loading="saving" :disabled="preview === (info?.signature || '')" @click="save">
              保存签名
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { getMe, updateSignature } from '@/api/user'

const userStore = useUserStore()
const info = ref(null)
const preview = ref('')
const saving = ref(false)
const hasSig = computed(() => !!preview.value)

async function refresh() {
  info.value = await getMe()
  preview.value = info.value.signature || ''
  userStore.setUserInfo(info.value)
}

function onFileChange(file) {
  const raw = file.raw
  if (!raw) return
  if (!raw.type.startsWith('image/')) {
    ElMessage.error('请选择图片文件')
    return
  }
  const reader = new FileReader()
  reader.onload = (e) => {
    preview.value = e.target.result // data-URI
    ElMessage.success('已载入签名图片，点击"保存签名"生效')
  }
  reader.readAsDataURL(raw)
}

function reset() {
  preview.value = info.value?.signature || ''
}

async function save() {
  saving.value = true
  try {
    const res = await updateSignature(preview.value)
    info.value = res
    preview.value = res.signature || ''
    userStore.setUserInfo(res)
    ElMessage.success('签名已保存')
  } finally {
    saving.value = false
  }
}

onMounted(refresh)
</script>

<style scoped lang="scss">
.mb { margin-bottom: 14px; }
.sig-header { display: flex; align-items: center; gap: 8px; }
.sig-preview { margin-bottom: 14px; }
.sig-label { font-size: 13px; color: #909399; margin-bottom: 6px; }
.sig-box {
  border: 1px dashed rgba(96,150,210,0.3);
  border-radius: 8px;
  min-height: 92px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(28,155,230,0.06);
}
.sig-img { max-height: 80px; max-width: 100%; }
.sig-upload {
  :deep(.el-upload),
  :deep(.el-upload-dragger) { width: 100%; }
  :deep(.el-upload-dragger) { padding: 16px; }
}
.sig-actions {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
