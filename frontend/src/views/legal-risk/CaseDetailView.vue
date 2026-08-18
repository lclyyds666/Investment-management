<template>
  <section class="case-detail" v-loading="loading">
    <header class="case-header">
      <el-button :icon="ArrowLeft" text circle aria-label="返回案件列表" @click="$router.push('/investment/legal-risk/cases')" />
      <div class="case-title">
        <div><span class="case-no">{{ caseData.case_no || '草稿未编号' }}</span><el-tag v-if="caseData.archived_at" type="info">已归档</el-tag></div>
        <h1>{{ caseData.case_name || '案件详情' }}</h1>
        <p>{{ caseData.court_case_no || '暂无法院案号' }} · {{ caseData.court || '暂未填写受理法院' }}</p>
      </div>
      <div class="case-actions">
        <el-button v-if="canEdit && !readonly" :icon="Edit" @click="$router.push(`/investment/legal-risk/cases/${caseId}/edit`)">编辑</el-button>
        <el-button v-if="canEdit && caseData.stage === 'formal' && !readonly" @click="statusDialog.visible = true">变更状态</el-button>
        <el-button v-if="canActivate && caseData.stage === 'draft'" type="primary" :icon="CircleCheck" @click="activate">正式建档</el-button>
        <el-button v-if="canArchive && caseData.status === 'closed' && !readonly" @click="openArchive">归档</el-button>
        <el-button v-if="isSuperuser && readonly" @click="openUnarchive">解除归档</el-button>
      </div>
    </header>

    <el-alert v-if="caseData.stage === 'draft'" type="info" :closable="false" show-icon class="draft-alert">
      <template #title>草稿不生成案件编号，不进入统计、预警或钉钉通知。正式建档前需补齐原告/申请人和被告/被申请人。</template>
    </el-alert>

    <div class="key-metrics">
      <div><span>主状态</span><strong>{{ caseData.stage === 'draft' ? '草稿' : caseStatusLabel(caseData.status) }}</strong></div>
      <div><span>标的额</span><strong>¥ {{ money(caseData.money?.subject_amount ?? caseData.subject_amount) }}</strong></div>
      <div><span>执行依据金额</span><strong>¥ {{ money(caseData.money?.executable_amount) }}</strong></div>
      <div><span>累计回款</span><strong>¥ {{ money(caseData.money?.recovered_amount) }}</strong></div>
      <div><span>待回款</span><strong>¥ {{ money(caseData.money?.outstanding_amount) }}</strong></div>
    </div>

    <div class="tabs-shell">
      <el-tabs v-model="activeTab">
        <el-tab-pane v-for="tab in CASE_DETAIL_TABS" :key="tab.name" :name="tab.name" :label="tab.label" />
      </el-tabs>

      <div v-if="activeTab === 'overview'" class="tab-content">
        <section class="detail-section">
          <h2>案件概览</h2>
          <el-descriptions :column="descriptionColumns" border>
            <el-descriptions-item label="案由">{{ caseData.cause_of_action || '-' }}</el-descriptions-item>
            <el-descriptions-item label="负责人">{{ userName(caseData.responsible_user_id) }}</el-descriptions-item>
            <el-descriptions-item label="保密等级">{{ caseData.confidentiality_level === 'confidential' ? '机密' : '内部' }}</el-descriptions-item>
            <el-descriptions-item label="律师事务所">{{ caseData.law_firm || '-' }}</el-descriptions-item>
            <el-descriptions-item label="承办律师">{{ caseData.attorney_name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="结案日期">{{ caseData.closed_date || '-' }}</el-descriptions-item>
            <el-descriptions-item label="案情摘要" :span="descriptionColumns">{{ caseData.case_summary || '-' }}</el-descriptions-item>
            <el-descriptions-item label="诉讼/仲裁请求" :span="descriptionColumns">{{ caseData.claims || '-' }}</el-descriptions-item>
            <el-descriptions-item label="可执行财产" :span="descriptionColumns">{{ caseData.enforcement_property_status || '-' }}</el-descriptions-item>
            <el-descriptions-item label="结案摘要" :span="descriptionColumns">{{ caseData.closure_summary || '-' }}</el-descriptions-item>
          </el-descriptions>
        </section>

        <section class="detail-section">
          <div class="section-head"><h2>当事人</h2><el-button v-if="canManage && !readonly" type="primary" plain :icon="Plus" @click="openDialog('party')">新增当事人</el-button></div>
          <el-table :data="caseData.parties" stripe>
            <el-table-column label="诉讼地位" width="130"><template #default="{ row }">{{ partyTypeLabel(row.party_type) }}</template></el-table-column>
            <el-table-column prop="name" label="名称" min-width="180" />
            <el-table-column prop="identity_no" label="证件/统一代码" min-width="170" />
            <el-table-column prop="contact" label="联系方式" min-width="130" />
            <el-table-column prop="address" label="地址" min-width="180" show-overflow-tooltip />
            <el-table-column v-if="canManage && !readonly" label="操作" width="120"><template #default="{ row }"><el-button link type="primary" @click="openDialog('party', row)">编辑</el-button><el-button link type="danger" @click="removeParty(row)">删除</el-button></template></el-table-column>
          </el-table>
          <el-empty v-if="!caseData.parties?.length" description="尚未登记当事人" :image-size="60" />
        </section>

        <section class="detail-section">
          <div class="section-head"><h2>协同人员</h2><el-button v-if="canManage && !readonly" type="primary" plain :icon="Plus" @click="openDialog('collaborator')">指派人员</el-button></div>
          <el-table :data="caseData.collaborators" stripe>
            <el-table-column label="人员" min-width="180"><template #default="{ row }">{{ userName(row.user_id) }}</template></el-table-column>
            <el-table-column label="类型" width="120"><template #default="{ row }">{{ row.collaborator_type === 'legal_counsel' ? '外聘法律顾问' : '协同人员' }}</template></el-table-column>
            <el-table-column prop="effective_at" label="生效时间" min-width="170" />
            <el-table-column prop="expires_at" label="到期时间" min-width="170" />
            <el-table-column v-if="canManage && !readonly" label="操作" width="76"><template #default="{ row }"><el-button link type="danger" @click="removeCollaborator(row)">移除</el-button></template></el-table-column>
          </el-table>
          <el-empty v-if="!caseData.collaborators?.length" description="尚未指派协同人员" :image-size="60" />
        </section>
      </div>

      <div v-else-if="activeTab === 'judgments'" class="tab-content">
        <SectionTitle title="裁判与结果明细" :writable="canManage && !readonly" @add="openDialog('judgment')" />
        <el-table :data="caseData.judgments" stripe>
          <el-table-column label="类型" width="100"><template #default="{ row }">{{ judgmentTypeLabel(row.judgment_type) }}</template></el-table-column>
          <el-table-column prop="summary" label="结果摘要" min-width="240" show-overflow-tooltip />
          <el-table-column prop="judgment_date" label="裁判日期" width="110" />
          <el-table-column prop="performance_deadline" label="履行期限" width="110" />
          <el-table-column label="判决金额" width="140" align="right"><template #default="{ row }">{{ money(row.executable_amount) }}</template></el-table-column>
          <el-table-column label="当前执行依据" width="120"><template #default="{ row }"><el-tag v-if="row.is_current_enforcement_basis" type="success">是</el-tag><span v-else>-</span></template></el-table-column>
          <el-table-column v-if="canManage && !readonly" label="操作" width="120"><template #default="{ row }"><el-button link type="primary" @click="openDialog('judgment', row)">编辑</el-button><el-button link type="danger" @click="removeDetail('judgments', row)">删除</el-button></template></el-table-column>
        </el-table>
      </div>

      <div v-else-if="activeTab === 'assets'" class="tab-content">
        <SectionTitle title="查封、扣押、冻结资产" :writable="canManage && !readonly" @add="openDialog('asset')" />
        <el-table :data="caseData.assets" stripe>
          <el-table-column prop="asset_type" label="资产类型" width="110" />
          <el-table-column prop="asset_name" label="资产名称" min-width="210" show-overflow-tooltip />
          <el-table-column prop="measure_type" label="措施" width="110" />
          <el-table-column prop="expiry_date" label="到期日" width="110" />
          <el-table-column label="剩余天数" width="100" align="right"><template #default="{ row }"><span :class="{ urgent: row.remaining_days !== null && row.remaining_days <= 7 }">{{ row.remaining_days ?? '-' }}</span></template></el-table-column>
          <el-table-column prop="disposal_status" label="处置状态" min-width="120" />
          <el-table-column v-if="canManage && !readonly" label="操作" width="120"><template #default="{ row }"><el-button link type="primary" @click="openDialog('asset', row)">编辑</el-button><el-button link type="danger" @click="removeDetail('assets', row)">删除</el-button></template></el-table-column>
        </el-table>
      </div>

      <div v-else-if="activeTab === 'recoveries'" class="tab-content">
        <SectionTitle title="清收回款与止损" :writable="canManage && !readonly" @add="openDialog('recovery')" />
        <el-table :data="caseData.recoveries" stripe>
          <el-table-column label="类型" width="120"><template #default="{ row }">{{ recoveryTypeLabel(row.recovery_type) }}</template></el-table-column>
          <el-table-column prop="recovery_date" label="发生日期" width="120" />
          <el-table-column label="金额（元）" width="160" align="right"><template #default="{ row }"><span class="amount">{{ money(row.amount) }}</span></template></el-table-column>
          <el-table-column prop="source_description" label="来源说明" min-width="240" show-overflow-tooltip />
          <el-table-column v-if="canManage && !readonly" label="操作" width="120"><template #default="{ row }"><el-button link type="primary" @click="openDialog('recovery', row)">编辑</el-button><el-button link type="danger" @click="removeDetail('recoveries', row)">删除</el-button></template></el-table-column>
        </el-table>
      </div>

      <div v-else-if="activeTab === 'progress'" class="tab-content">
        <SectionTitle title="案件进展、风险点与法律意见" :writable="(canManage || canCounselWrite) && !readonly" @add="openDialog('progress')" />
        <el-timeline v-if="caseData.progress_records?.length">
          <el-timeline-item v-for="row in caseData.progress_records" :key="row.id" :timestamp="formatTime(row.recorded_at)" placement="top">
            <div class="timeline-record">
              <div class="record-head"><el-tag effect="plain">{{ progressTypeLabel(row.progress_type) }}</el-tag><div><el-button v-if="canEditProgress(row) && !readonly" link type="primary" @click="openDialog('progress', row)">编辑</el-button><el-button v-if="canManage && !readonly" link type="danger" @click="removeDetail('progress', row)">删除</el-button></div></div>
              <p>{{ row.content }}</p>
              <dl v-if="row.risk_points"><dt>风险点</dt><dd>{{ row.risk_points }}</dd></dl>
              <dl v-if="row.next_plan"><dt>下一步</dt><dd>{{ row.next_plan }}</dd></dl>
            </div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="尚未登记进展或法律意见" />
      </div>

      <div v-else-if="activeTab === 'deadlines'" class="tab-content">
        <SectionTitle title="开庭、缴费、材料及自定义期限" :writable="canManage && !readonly" @add="openDialog('deadline')" />
        <el-table :data="caseData.deadlines" stripe>
          <el-table-column label="类型" width="130"><template #default="{ row }">{{ deadlineTypeLabel(row.deadline_type) }}</template></el-table-column>
          <el-table-column prop="title" label="事项" min-width="220" />
          <el-table-column prop="event_date" label="截止日" width="110" />
          <el-table-column prop="reminder_days" label="提前提醒" width="100" align="right" />
          <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.is_completed ? 'success' : 'warning'">{{ row.is_completed ? '已完成' : '待完成' }}</el-tag></template></el-table-column>
          <el-table-column prop="completion_note" label="完成结果" min-width="180" show-overflow-tooltip />
          <el-table-column v-if="canManage && !readonly" label="操作" width="174"><template #default="{ row }"><el-button link type="primary" @click="openDialog('deadline', row)">编辑</el-button><el-button v-if="!row.is_completed" link type="success" @click="finishDeadline(row)">办结</el-button><el-button link type="danger" @click="removeDetail('deadlines', row)">删除</el-button></template></el-table-column>
        </el-table>
      </div>

      <div v-else-if="activeTab === 'attachments'" class="tab-content">
        <SectionTitle title="案件材料" :writable="canUpload && !readonly" @add="openDialog('attachment')" />
        <el-table :data="attachments" stripe>
          <el-table-column prop="original_name" label="文件名" min-width="250" show-overflow-tooltip />
          <el-table-column prop="category" label="材料分类" width="130" />
          <el-table-column label="大小" width="100" align="right"><template #default="{ row }">{{ fileSize(row.size_bytes) }}</template></el-table-column>
          <el-table-column label="上传时间" min-width="170"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column>
          <el-table-column label="操作" width="170"><template #default="{ row }"><el-button v-if="['.pdf','.png','.jpg','.jpeg'].includes(row.extension)" link type="primary" @click="downloadFile(row, 'preview')">预览</el-button><el-button link @click="downloadFile(row)">下载</el-button><el-button v-if="mayDeleteAttachment(row)" link type="danger" @click="removeAttachment(row)">删除</el-button></template></el-table-column>
        </el-table>
      </div>

      <div v-else class="tab-content">
        <el-timeline v-if="activities.length">
          <el-timeline-item v-for="item in activities" :key="item.id" :timestamp="formatTime(item.created_at)" placement="top">
            <div class="activity"><strong>{{ activityLabel(item.action) }}</strong><span>{{ item.actor_name || '-' }}</span><p v-if="item.summary">{{ item.summary }}</p></div>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无操作记录" />
      </div>
    </div>

    <el-dialog v-model="entryDialog.visible" :title="entryDialogTitle" width="620px" destroy-on-close>
      <el-form ref="entryForm" :model="entryDialog.form" label-position="top">
        <template v-if="entryDialog.type === 'party'">
          <el-form-item label="诉讼地位" required><el-select v-model="entryDialog.form.party_type"><el-option v-for="item in PARTY_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
          <el-form-item label="名称" required><el-input v-model="entryDialog.form.name" /></el-form-item>
          <el-form-item label="证件类型"><el-select v-model="entryDialog.form.identity_type"><el-option label="组织机构" value="organization" /><el-option label="自然人" value="individual" /></el-select></el-form-item>
          <el-form-item label="证件号/统一社会信用代码"><el-input v-model="entryDialog.form.identity_no" /></el-form-item>
          <el-form-item label="联系方式"><el-input v-model="entryDialog.form.contact" /></el-form-item>
          <el-form-item label="地址"><el-input v-model="entryDialog.form.address" /></el-form-item>
        </template>
        <template v-else-if="entryDialog.type === 'collaborator'">
          <el-form-item label="协同人员" required><el-input v-model="entryDialog.form.user_name" clearable maxlength="64" placeholder="请输入与账号姓名一致的姓名" /></el-form-item>
          <el-form-item label="协同类型"><el-select v-model="entryDialog.form.collaborator_type"><el-option label="协同人员" value="collaborator" /><el-option label="外聘法律顾问" value="legal_counsel" /></el-select></el-form-item>
          <el-form-item label="授权到期时间"><el-date-picker v-model="entryDialog.form.expires_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" /></el-form-item>
        </template>
        <template v-else-if="entryDialog.type === 'judgment'">
          <el-form-item label="裁判/结果类型" required><el-select v-model="entryDialog.form.judgment_type"><el-option v-for="item in JUDGMENT_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
          <el-form-item label="结果摘要"><el-input v-model="entryDialog.form.summary" type="textarea" :rows="4" /></el-form-item>
          <div class="dialog-grid"><el-form-item label="裁判日期"><el-date-picker v-model="entryDialog.form.judgment_date" value-format="YYYY-MM-DD" /></el-form-item><el-form-item label="生效日期"><el-date-picker v-model="entryDialog.form.effective_date" value-format="YYYY-MM-DD" /></el-form-item></div>
          <div class="dialog-grid"><el-form-item label="履行期限"><el-date-picker v-model="entryDialog.form.performance_deadline" value-format="YYYY-MM-DD" /></el-form-item><el-form-item label="判决金额"><el-input-number v-model="entryDialog.form.executable_amount" :min="0" :precision="2" :controls="false" /></el-form-item></div>
          <el-checkbox v-model="entryDialog.form.is_current_enforcement_basis">设为当前执行依据</el-checkbox>
        </template>
        <template v-else-if="entryDialog.type === 'asset'">
          <div class="dialog-grid"><el-form-item label="资产类型" required><el-input v-model="entryDialog.form.asset_type" /></el-form-item><el-form-item label="保全措施" required><el-input v-model="entryDialog.form.measure_type" placeholder="查封/扣押/冻结" /></el-form-item></div>
          <el-form-item label="资产名称" required><el-input v-model="entryDialog.form.asset_name" /></el-form-item>
          <div class="dialog-grid"><el-form-item label="开始日期"><el-date-picker v-model="entryDialog.form.start_date" value-format="YYYY-MM-DD" /></el-form-item><el-form-item label="到期日期"><el-date-picker v-model="entryDialog.form.expiry_date" value-format="YYYY-MM-DD" /></el-form-item></div>
          <div class="dialog-grid"><el-form-item label="提前提醒天数"><el-input-number v-model="entryDialog.form.reminder_days" :min="0" :max="365" /></el-form-item><el-form-item label="处置状态"><el-input v-model="entryDialog.form.disposal_status" /></el-form-item></div>
          <el-form-item label="备注"><el-input v-model="entryDialog.form.notes" type="textarea" /></el-form-item>
        </template>
        <template v-else-if="entryDialog.type === 'recovery'">
          <el-form-item label="类型" required><el-select v-model="entryDialog.form.recovery_type"><el-option v-for="item in RECOVERY_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
          <div class="dialog-grid"><el-form-item label="发生日期" required><el-date-picker v-model="entryDialog.form.recovery_date" value-format="YYYY-MM-DD" /></el-form-item><el-form-item label="金额（元）" required><el-input-number v-model="entryDialog.form.amount" :min="0.01" :precision="2" :controls="false" /></el-form-item></div>
          <el-form-item label="来源说明"><el-input v-model="entryDialog.form.source_description" type="textarea" /></el-form-item>
        </template>
        <template v-else-if="entryDialog.type === 'progress'">
          <el-form-item label="记录类型"><el-select v-model="entryDialog.form.progress_type" :disabled="canCounselWrite && !canManage"><el-option v-for="item in PROGRESS_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
          <el-form-item label="进展/意见内容" required><el-input v-model="entryDialog.form.content" type="textarea" :rows="5" /></el-form-item>
          <el-form-item label="风险点"><el-input v-model="entryDialog.form.risk_points" type="textarea" :rows="3" /></el-form-item>
          <el-form-item label="下一步计划"><el-input v-model="entryDialog.form.next_plan" type="textarea" :rows="3" /></el-form-item>
          <el-form-item label="计划日期"><el-date-picker v-model="entryDialog.form.planned_date" value-format="YYYY-MM-DD" /></el-form-item>
        </template>
        <template v-else-if="entryDialog.type === 'deadline'">
          <el-form-item label="期限类型"><el-select v-model="entryDialog.form.deadline_type"><el-option v-for="item in DEADLINE_TYPE_OPTIONS" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
          <el-form-item label="事项标题" required><el-input v-model="entryDialog.form.title" /></el-form-item>
          <div class="dialog-grid"><el-form-item label="截止日期" required><el-date-picker v-model="entryDialog.form.event_date" value-format="YYYY-MM-DD" /></el-form-item><el-form-item label="提前提醒天数"><el-input-number v-model="entryDialog.form.reminder_days" :min="0" :max="365" /></el-form-item></div>
          <el-form-item label="负责人"><el-select v-model="entryDialog.form.responsible_user_id" clearable filterable><el-option v-for="user in users" :key="user.id" :label="user.name" :value="user.id" /></el-select></el-form-item>
        </template>
        <template v-else-if="entryDialog.type === 'attachment'">
          <el-form-item label="材料分类"><el-select v-model="entryDialog.form.category"><el-option label="诉讼材料" value="litigation" /><el-option label="裁判文书" value="judgment" /><el-option label="执行材料" value="enforcement" /><el-option label="证据材料" value="evidence" /><el-option label="其他" value="other" /></el-select></el-form-item>
          <el-upload drag :auto-upload="false" :limit="1" accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg" :on-change="(file) => entryDialog.form.file = file.raw" :on-remove="() => entryDialog.form.file = null">
            <el-icon class="upload-icon"><UploadFilled /></el-icon><div>选择文件，单个文件不超过 50 MB</div>
          </el-upload>
        </template>
      </el-form>
      <template #footer><el-button @click="entryDialog.visible = false">取消</el-button><el-button type="primary" :loading="entryDialog.saving" @click="submitEntry">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="statusDialog.visible" title="变更案件主状态" width="480px">
      <el-form label-position="top"><el-form-item label="新状态" required><el-select v-model="statusDialog.status"><el-option v-for="item in CASE_STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item><el-form-item v-if="statusDialog.status === 'terminal'" label="终本日期"><el-date-picker v-model="statusDialog.terminal_date" value-format="YYYY-MM-DD" /></el-form-item></el-form>
      <template #footer><el-button @click="statusDialog.visible = false">取消</el-button><el-button type="primary" :loading="statusDialog.saving" @click="changeStatus">确认变更</el-button></template>
    </el-dialog>
  </section>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, reactive, ref } from 'vue'
import { ArrowLeft, CircleCheck, Edit, Plus } from '@element-plus/icons-vue'
import { ElButton, ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import {
  activateCase, archiveCase, completeDeadline, createAsset, createCollaborator,
  createDeadline, createJudgment, createParty, createProgress, createRecovery,
  deleteAttachment, deleteCollaborator, deleteDetail, deleteParty, fetchAttachment, getCase,
  listActivities, listAttachments, listLegalUserOptions, unarchiveCase,
  updateAsset, updateCaseStatus, updateDeadline, updateJudgment, updateParty,
  updateProgress, updateRecovery, uploadAttachment
} from '@/api/legalRisk'
import { usePortalStore } from '@/store/portal'
import { useUserStore } from '@/store/user'
import { roleLabel } from '@/constants/business'
import {
  CASE_STATUS_OPTIONS, DEADLINE_TYPE_OPTIONS, JUDGMENT_TYPE_OPTIONS, PARTY_TYPE_OPTIONS,
  PROGRESS_TYPE_OPTIONS, RECOVERY_TYPE_OPTIONS, caseStatusLabel, deadlineTypeLabel,
  judgmentTypeLabel, money, partyTypeLabel, progressTypeLabel, recoveryTypeLabel
} from '@/constants/legalRisk'
import { CASE_DETAIL_TABS } from './caseDetailTabs'
import {
  LEGAL_CAPABILITIES,
  canDeleteLegalAttachment,
  hasLegalCapability
} from '@/utils/legalCapabilities'

const SectionTitle = defineComponent({
  props: { title: String, writable: Boolean }, emits: ['add'],
  setup(props, { emit }) { return () => h('div', { class: 'section-head' }, [h('h2', props.title), props.writable ? h(ElButton, { type: 'primary', plain: true, icon: Plus, onClick: () => emit('add') }, () => '新增') : null]) }
})

const route = useRoute()
const portalStore = usePortalStore()
const userStore = useUserStore()
const caseId = Number(route.params.caseId)
const loading = ref(true)
const activeTab = ref('overview')
const caseData = reactive({ parties: [], collaborators: [], judgments: [], assets: [], recoveries: [], progress_records: [], deadlines: [], money: {} })
const users = ref([])
const attachments = ref([])
const activities = ref([])
const role = computed(() => portalStore.companyRole('investment'))
const isSuperuser = computed(() => portalStore.isSuperuser)
const hasCapability = (capability) => hasLegalCapability(role.value, capability, isSuperuser.value, portalStore.assignments)
const canManage = computed(() => hasCapability(LEGAL_CAPABILITIES.MANAGE_DETAIL))
const canEdit = computed(() => hasCapability(LEGAL_CAPABILITIES.EDIT_CASE))
const canActivate = computed(() => hasCapability(LEGAL_CAPABILITIES.ACTIVATE_CASE))
const canArchive = computed(() => hasCapability(LEGAL_CAPABILITIES.ARCHIVE_CASE))
const canCounselWrite = computed(() => hasCapability(LEGAL_CAPABILITIES.ADD_COUNSEL_CONTENT))
const canUpload = computed(() => hasCapability(LEGAL_CAPABILITIES.UPLOAD_ATTACHMENT))
const readonly = computed(() => Boolean(caseData.archived_at))
const descriptionColumns = computed(() => window.innerWidth < 720 ? 1 : 3)
const entryDialog = reactive({ visible: false, saving: false, type: '', rowId: null, form: {} })
const statusDialog = reactive({ visible: false, saving: false, status: '', terminal_date: null })

const dialogTitles = { party: '新增当事人', collaborator: '指派协同人员', judgment: '新增裁判结果', asset: '新增查扣冻资产', recovery: '新增清回止损', progress: '新增进展风险', deadline: '新增期限事件', attachment: '上传案件材料' }
const entryDialogTitle = computed(() => {
  const title = dialogTitles[entryDialog.type] || '新增记录'
  return entryDialog.rowId ? title.replace('新增', '编辑') : title
})
const userName = (id) => users.value.find((item) => item.id === id)?.name || (id ? `用户 #${id}` : '-')
const formatTime = (value) => value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '-'
const fileSize = (bytes) => bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`
const activityLabel = (action) => ({ create_draft: '创建草稿', update: '更新案件', activate: '正式建档', status_change: '变更状态', archive: '归档案件', unarchive: '解除归档', upload_attachment: '上传附件', download_attachment: '下载附件' }[action] || action)
const canEditProgress = (row) => canManage.value || (
  canCounselWrite.value
  && row.progress_type === 'legal_opinion'
  && Number(row.registered_by) === Number(userStore.userInfo?.id)
)
const mayDeleteAttachment = (row) => canDeleteLegalAttachment({
  role: role.value,
  isSuperuser: isSuperuser.value,
  currentUserId: userStore.userInfo?.id,
  archivedAt: caseData.archived_at,
  assignments: portalStore.assignments
}, row)

async function load() {
  loading.value = true
  try {
    const [detail, userRows, files, logs] = await Promise.all([getCase(caseId), listLegalUserOptions(), listAttachments(caseId), listActivities(caseId)])
    Object.assign(caseData, detail)
    users.value = userRows || []
    attachments.value = files || []
    activities.value = logs || []
    statusDialog.status = detail.status || 'review_filing'
  } finally { loading.value = false }
}

function defaultForm(type) {
  const defaults = {
    party: { party_type: 'plaintiff', name: '', identity_type: 'organization', identity_no: '', contact: '', address: '', sort_order: 0 },
    collaborator: { user_name: '', collaborator_type: 'collaborator', expires_at: null },
    judgment: { judgment_type: 'first_instance', summary: '', judgment_date: null, effective_date: null, performance_deadline: null, executable_amount: null, is_current_enforcement_basis: false, sort_order: 0 },
    asset: { asset_type: '', asset_name: '', measure_type: '', priority_type: '', start_date: null, expiry_date: null, reminder_days: 30, disposal_status: '', notes: '' },
    recovery: { recovery_type: 'recovery', recovery_date: new Date().toISOString().slice(0, 10), amount: null, source_description: '' },
    progress: { progress_type: canCounselWrite.value && !canManage.value ? 'legal_opinion' : 'progress', content: '', risk_points: '', next_plan: '', responsible_user_id: null, planned_date: null },
    deadline: { deadline_type: 'hearing', title: '', event_date: null, reminder_days: 7, responsible_user_id: null },
    attachment: { category: 'other', file: null }
  }
  return defaults[type]
}
function openDialog(type, row = null) {
  const form = defaultForm(type)
  if (row) {
    Object.keys(form).forEach((field) => {
      if (row[field] !== undefined) form[field] = row[field]
    })
  }
  entryDialog.type = type
  entryDialog.rowId = row?.id || null
  entryDialog.form = form
  entryDialog.visible = true
}

function validateEntry() {
  const f = entryDialog.form
  const ok = {
    party: f.name, collaborator: f.user_name?.trim(), judgment: f.judgment_type,
    asset: f.asset_type && f.asset_name && f.measure_type,
    recovery: f.recovery_date && Number(f.amount) > 0,
    progress: f.content, deadline: f.title && f.event_date, attachment: f.file
  }[entryDialog.type]
  if (!ok) { ElMessage.warning('请填写必填项'); return false }
  return true
}

async function submitEntry() {
  if (!validateEntry()) return
  entryDialog.saving = true
  try {
    const createFuncs = { party: createParty, collaborator: createCollaborator, judgment: createJudgment, asset: createAsset, recovery: createRecovery, progress: createProgress, deadline: createDeadline }
    const updateFuncs = { party: updateParty, judgment: updateJudgment, asset: updateAsset, recovery: updateRecovery, progress: updateProgress, deadline: updateDeadline }
    if (entryDialog.type === 'attachment') {
      const data = new FormData(); data.append('case_id', String(caseId)); data.append('related_type', 'case'); data.append('category', entryDialog.form.category); data.append('file', entryDialog.form.file)
      await uploadAttachment(data)
    } else if (entryDialog.rowId) {
      await updateFuncs[entryDialog.type](caseId, entryDialog.rowId, entryDialog.form)
    } else {
      const payload = entryDialog.type === 'collaborator'
        ? { ...entryDialog.form, user_name: entryDialog.form.user_name.trim() }
        : entryDialog.form
      await createFuncs[entryDialog.type](caseId, payload)
    }
    entryDialog.visible = false
    ElMessage.success('记录已保存')
    await load()
  } finally { entryDialog.saving = false }
}

async function activate() {
  const hasPlaintiff = caseData.parties.some((row) => row.party_type === 'plaintiff')
  const hasDefendant = caseData.parties.some((row) => row.party_type === 'defendant')
  if (!hasPlaintiff || !hasDefendant) return ElMessage.warning('正式建档前必须至少登记一名原告/申请人和一名被告/被申请人')
  await ElMessageBox.confirm('正式建档后将生成案件编号并进入统计与预警，是否继续？', '确认正式建档', { type: 'warning' })
  await activateCase(caseId); ElMessage.success('正式建档成功'); load()
}

async function changeStatus() {
  if (!statusDialog.status) return ElMessage.warning('请选择新状态')
  statusDialog.saving = true
  try {
    await updateCaseStatus(caseId, { status: statusDialog.status, version: caseData.version, terminal_date: statusDialog.terminal_date })
    statusDialog.visible = false; ElMessage.success('案件状态已更新'); load()
  } finally { statusDialog.saving = false }
}
async function openArchive() { const { value } = await ElMessageBox.prompt('请输入归档说明', '归档案件', { inputValidator: (v) => Boolean(v?.trim()) || '归档说明不能为空' }); await archiveCase(caseId, value); ElMessage.success('案件已归档'); load() }
async function openUnarchive() { const { value } = await ElMessageBox.prompt('请输入解除归档原因', '解除归档', { inputValidator: (v) => Boolean(v?.trim()) || '原因不能为空' }); await unarchiveCase(caseId, value); ElMessage.success('已解除归档'); load() }
async function removeParty(row) { await ElMessageBox.confirm('确认删除该当事人？', '删除确认', { type: 'warning' }); await deleteParty(caseId, row.id); load() }
async function removeCollaborator(row) { await ElMessageBox.confirm('确认移除该协同人员？', '移除确认', { type: 'warning' }); await deleteCollaborator(caseId, row.id); load() }
async function removeDetail(type, row) { await ElMessageBox.confirm('确认删除该条记录？', '删除确认', { type: 'warning' }); await deleteDetail(caseId, type, row.id); load() }
async function finishDeadline(row) { const { value } = await ElMessageBox.prompt('请填写期限事项办理结果', '办结期限', { inputValidator: (v) => Boolean(v?.trim()) || '办理结果不能为空' }); await completeDeadline(caseId, row.id, value); ElMessage.success('期限事项已办结'); load() }
async function removeAttachment(row) { await ElMessageBox.confirm('确认删除该附件记录？', '删除确认', { type: 'warning' }); await deleteAttachment(row.id); load() }
async function downloadFile(row, mode = 'download') {
  const blob = await fetchAttachment(row.id, mode)
  const url = URL.createObjectURL(blob)
  if (mode === 'preview') window.open(url, '_blank', 'noopener,noreferrer')
  else { const link = document.createElement('a'); link.href = url; link.download = row.original_name; link.click() }
  setTimeout(() => URL.revokeObjectURL(url), 30000)
}
onMounted(load)
</script>

<style scoped>
.case-detail { min-width: 0; }
.case-header { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 14px; margin-bottom: 14px; }
.case-title { min-width: 0; }
.case-title > div { display: flex; align-items: center; gap: 8px; }
.case-no { color: var(--brand-vermilion); font-family: var(--font-data); font-size: 12px; font-weight: 700; }
.case-title h1 { margin: 5px 0 3px; overflow-wrap: anywhere; font-size: 24px; letter-spacing: 0; }
.case-title p { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; }
.case-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; }
.draft-alert { margin-bottom: 14px; }
.key-metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); margin-bottom: 14px; border: 1px solid var(--el-border-color-lighter); background: var(--surface-solid); }
.key-metrics > div { display: flex; min-width: 0; min-height: 82px; padding: 14px 16px; flex-direction: column; border-right: 1px solid var(--el-border-color-lighter); }
.key-metrics > div:last-child { border-right: 0; }
.key-metrics span { color: var(--el-text-color-secondary); font-size: 12px; }
.key-metrics strong { margin-top: 8px; overflow: hidden; text-overflow: ellipsis; font-family: var(--font-data); font-size: 18px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.tabs-shell { min-width: 0; padding: 0 18px 18px; border: 1px solid var(--el-border-color-lighter); background: var(--surface-solid); }
.tab-content { min-width: 0; overflow-x: auto; }
.detail-section { margin-bottom: 24px; }
.detail-section h2, :deep(.section-head h2) { margin: 0; font-size: 16px; letter-spacing: 0; }
.section-head, :deep(.section-head) { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; padding-left: 10px; border-left: 3px solid var(--divider-rail); }
.amount { font-family: var(--font-data); font-variant-numeric: tabular-nums; }
.urgent { color: var(--el-color-danger); font-weight: 700; }
.timeline-record, .activity { padding: 14px; border: 1px solid var(--el-border-color-lighter); background: var(--surface-muted); }
.record-head { display: flex; align-items: center; justify-content: space-between; }
.timeline-record p { white-space: pre-wrap; }
.timeline-record dl { display: grid; grid-template-columns: 64px minmax(0, 1fr); margin: 8px 0 0; }
.timeline-record dt { color: var(--el-text-color-secondary); }
.timeline-record dd { margin: 0; white-space: pre-wrap; }
.activity { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px 14px; }
.activity span { color: var(--el-text-color-secondary); }
.activity p { grid-column: 1 / -1; margin: 0; }
.dialog-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.dialog-grid :deep(.el-date-editor), .dialog-grid :deep(.el-input-number), :deep(.el-select) { width: 100%; }
.upload-icon { font-size: 38px; }
@media (max-width: 960px) { .key-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } .key-metrics > div { border-bottom: 1px solid var(--el-border-color-lighter); } }
@media (max-width: 720px) { .case-header { grid-template-columns: auto minmax(0, 1fr); align-items: flex-start; } .case-actions { grid-column: 1 / -1; justify-content: flex-start; } .tabs-shell { padding-inline: 12px; } .dialog-grid { grid-template-columns: 1fr; } }
</style>
