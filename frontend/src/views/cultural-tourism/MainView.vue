<template>
  <div class="ct-main">
    <div class="ct-heading">
      <div>
        <h1 class="ct-title">文旅业务</h1>
        <p class="ct-subtitle">选择景区，查看平台入口与核销数据台账</p>
      </div>
      <el-button v-if="canCreateScenic" type="primary" :icon="Plus" @click="openCreateDialog">
        新增景区
      </el-button>
    </div>

    <div class="ct-grid" v-loading="scenicStore.loading">
      <div
        v-for="spot in scenicStore.spots"
        :key="spot.id"
        class="ct-card"
        @click="goDetail(spot.id)"
      >
        <div class="ct-card-img">
          <img
            v-if="spot.image && !failed[spot.id]"
            :src="spot.image"
            :alt="spot.name"
            @error="failed[spot.id] = true"
          />
          <div v-else class="ct-card-fallback">
            <el-icon><Place /></el-icon>
          </div>
        </div>
        <div class="ct-card-name">{{ spot.name }}</div>
      </div>
    </div>
    <el-empty v-if="scenicStore.loaded && !scenicStore.spots.length" description="暂无已启用景区" />

    <el-dialog
      v-model="dialogVisible"
      title="新增景区"
      width="min(720px, 92vw)"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="118px">
        <el-divider content-position="left">基本信息</el-divider>
        <div class="form-grid">
          <el-form-item label="景区标识" prop="scenic_id">
            <el-input v-model.trim="form.scenic_id" maxlength="64" placeholder="例如：qingdao-scenic" />
          </el-form-item>
          <el-form-item label="景区名称" prop="scenic_name">
            <el-input v-model.trim="form.scenic_name" maxlength="128" />
          </el-form-item>
          <el-form-item label="展示顺序" prop="sort_order">
            <el-input-number v-model="form.sort_order" :min="0" :step="10" controls-position="right" />
          </el-form-item>
          <el-form-item label="启用景区">
            <el-switch v-model="form.enabled" />
          </el-form-item>
          <el-form-item label="景区图片" prop="image_url" class="span-2">
            <el-input v-model.trim="form.image_url" maxlength="500" placeholder="可填写公网 URL 或 /scenic/xxx.jpg" />
          </el-form-item>
        </div>

        <el-divider content-position="left">模块开关</el-divider>
        <div class="switch-row">
          <el-form-item label="门票台账"><el-switch v-model="form.ticket_enabled" /></el-form-item>
          <el-form-item label="酒店台账"><el-switch v-model="form.hotel_enabled" /></el-form-item>
        </div>

        <el-divider content-position="left">默认计算参数</el-divider>
        <div class="form-grid">
          <el-form-item label="核销率" prop="rate_hexiao">
            <el-input-number v-model="form.rate_hexiao" :min="0" :max="100" :precision="2" controls-position="right" />
            <span class="field-unit">%</span>
          </el-form-item>
          <el-form-item label="结算率" prop="rate_settle">
            <el-input-number v-model="form.rate_settle" :min="0" :max="100" :precision="2" controls-position="right" />
            <span class="field-unit">%</span>
          </el-form-item>
          <el-form-item label="佣金率" prop="commission_rate">
            <el-input-number v-model="form.commission_rate" :min="0" :max="100" :precision="2" controls-position="right" />
            <span class="field-unit">%</span>
          </el-form-item>
          <el-form-item label="酒店服务费算法" prop="hotel_fee_algo">
            <el-radio-group v-model="form.hotel_fee_algo">
              <el-radio-button :value="1">间夜算法</el-radio-button>
              <el-radio-button :value="2">结算率算法</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="每间夜服务费" prop="fee_per_night">
            <el-input-number v-model="form.fee_per_night" :min="0" :precision="2" controls-position="right" />
            <span class="field-unit">元</span>
          </el-form-item>
          <el-form-item label="门票产品默认值" class="span-2">
            <el-input v-model.trim="form.default_ticket_product" maxlength="200" />
          </el-form-item>
          <el-form-item label="酒店名称默认值" class="span-2">
            <el-input v-model.trim="form.default_hotel_name" maxlength="255" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">保存景区</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Place, Plus } from '@element-plus/icons-vue'
import { getScenicConfig, saveScenicConfig } from '@/api/scenic'
import { ROLES } from '@/constants/business'
import { useScenicStore } from '@/store/scenic'
import { useUserStore } from '@/store/user'
import {
  buildScenicConfigPayload,
  createDefaultScenicForm,
  SCENIC_ID_PATTERN
} from '@/utils/scenicConfigForm'

const router = useRouter()
const scenicStore = useScenicStore()
const userStore = useUserStore()
const failed = reactive({}) // 图片加载失败 → 降级占位
const canCreateScenic = computed(() => (
  userStore.isSuperuser ||
  userStore.role === ROLES.INFO_MAINTAINER ||
  userStore.role === ROLES.BUSINESS_HANDLER
))

const dialogVisible = ref(false)
const saving = ref(false)
const formRef = ref()
const form = reactive(createDefaultScenicForm())
const rules = {
  scenic_id: [
    { required: true, message: '请输入景区标识', trigger: 'blur' },
    { pattern: SCENIC_ID_PATTERN, message: '仅支持小写字母、数字和中划线', trigger: 'blur' }
  ],
  scenic_name: [{ required: true, message: '请输入景区名称', trigger: 'blur' }],
  image_url: [{ max: 500, message: '图片地址不能超过500个字符', trigger: 'blur' }],
  sort_order: [{ required: true, message: '请输入展示顺序', trigger: 'change' }],
  rate_hexiao: [{ required: true, message: '请输入核销率', trigger: 'change' }],
  rate_settle: [{ required: true, message: '请输入结算率', trigger: 'change' }],
  commission_rate: [{ required: true, message: '请输入佣金率', trigger: 'change' }],
  hotel_fee_algo: [{ required: true, message: '请选择酒店服务费算法', trigger: 'change' }],
  fee_per_night: [{ required: true, message: '请输入每间夜服务费', trigger: 'change' }]
}

onMounted(() => scenicStore.load(true).catch(() => {}))

function openCreateDialog() {
  Object.assign(form, createDefaultScenicForm())
  dialogVisible.value = true
  nextTick(() => formRef.value?.clearValidate())
}

async function submitCreate() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const current = await getScenicConfig(form.scenic_id)
    if (current.configured) {
      ElMessage.warning('该景区标识已存在，请更换后再保存。')
      return
    }
    await saveScenicConfig(form.scenic_id, buildScenicConfigPayload(form))
    delete failed[form.scenic_id]
    await scenicStore.load(true)
    dialogVisible.value = false
    ElMessage.success('景区已创建')
  } finally {
    saving.value = false
  }
}

function goDetail(id) {
  router.push(`/cultural-tourism/${id}`)
}
</script>

<style scoped lang="scss">
.ct-main {
  padding: 8px 4px 24px;
}
.ct-heading {
  position: relative;
  max-width: 1200px;
  margin: 0 auto 26px;
  > div { text-align: center; }
  > .el-button { position: absolute; right: 8px; top: 20px; }
}
.ct-title {
  text-align: center;
  margin: 18px 0 6px;
  font-size: 30px;
  font-weight: 800;
  letter-spacing: 4px;
  background: var(--chrome-title-gradient);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}
.ct-subtitle {
  text-align: center;
  margin: 0;
  color: var(--el-text-color-secondary);
  font-size: 14px;
}
/* Grid：每行严格 3 个卡片，卡片间距 40px */
.ct-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 40px;
  max-width: 1200px;
  margin: 0 auto;
  padding: 4px 8px 8px;
  box-sizing: border-box;
}
.ct-card {
  cursor: pointer;
  border-radius: 14px;
  overflow: hidden;
  box-shadow: var(--card-shadow);
  transition: transform 0.25s ease, box-shadow 0.25s ease;
  &:hover {
    transform: translateY(-4px);
    box-shadow: var(--card-shadow-hover);
  }
}
.ct-card-img {
  position: relative;
  height: 168px;
  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
}
.ct-card-name {
  padding: 10px 12px;
  font-size: 15px;
  font-weight: 700;
  text-align: center;
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-blank);
}
.ct-card-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0e2450, #1c9be6);
  .el-icon {
    font-size: 52px;
    color: rgba(255, 255, 255, 0.85);
  }
}
.form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  column-gap: 20px;
}
.span-2 { grid-column: 1 / -1; }
.switch-row {
  display: flex;
  gap: 36px;
  .el-form-item { margin-bottom: 0; }
}
.field-unit {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
}
@media (max-width: 720px) {
  .ct-heading {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
    > .el-button { position: static; }
  }
  .form-grid { grid-template-columns: 1fr; }
  .span-2 { grid-column: auto; }
}
</style>
