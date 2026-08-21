import request from './request'

const BASE = '/legal-risk'

export const listCases = (params) => request.get(`${BASE}/cases`, { params })
export const listLegalUserOptions = () => request.get(`${BASE}/user-options`)
export const listLegalInitiatorOptions = (resource) => request.get(`${BASE}/initiator-options`, { params: { resource } })
export const createCase = (data) => request.post(`${BASE}/cases`, data)
export const getCase = (id) => request.get(`${BASE}/cases/${id}`)
export const updateCase = (id, data) => request.put(`${BASE}/cases/${id}`, data)
export const deleteCase = (id) => request.delete(`${BASE}/cases/${id}`)
export const activateCase = (id) => request.post(`${BASE}/cases/${id}/activate`)
export const updateCaseStatus = (id, data) => request.post(`${BASE}/cases/${id}/status`, data)
export const archiveCase = (id, note) => request.post(`${BASE}/cases/${id}/archive`, { note })
export const unarchiveCase = (id, reason) => request.post(`${BASE}/cases/${id}/unarchive`, { reason })

export const createParty = (caseId, data) => request.post(`${BASE}/cases/${caseId}/parties`, data)
export const updateParty = (caseId, id, data) => request.put(`${BASE}/cases/${caseId}/parties/${id}`, data)
export const deleteParty = (caseId, id) => request.delete(`${BASE}/cases/${caseId}/parties/${id}`)
export const createCollaborator = (caseId, data) => request.post(`${BASE}/cases/${caseId}/collaborators`, data)
export const deleteCollaborator = (caseId, id) => request.delete(`${BASE}/cases/${caseId}/collaborators/${id}`)
export const createJudgment = (caseId, data) => request.post(`${BASE}/cases/${caseId}/judgments`, data)
export const updateJudgment = (caseId, id, data) => request.put(`${BASE}/cases/${caseId}/judgments/${id}`, data)
export const createAsset = (caseId, data) => request.post(`${BASE}/cases/${caseId}/assets`, data)
export const updateAsset = (caseId, id, data) => request.put(`${BASE}/cases/${caseId}/assets/${id}`, data)
export const createRecovery = (caseId, data) => request.post(`${BASE}/cases/${caseId}/recoveries`, data)
export const updateRecovery = (caseId, id, data) => request.put(`${BASE}/cases/${caseId}/recoveries/${id}`, data)
export const createProgress = (caseId, data) => request.post(`${BASE}/cases/${caseId}/progress`, data)
export const updateProgress = (caseId, id, data) => request.put(`${BASE}/cases/${caseId}/progress/${id}`, data)
export const createDeadline = (caseId, data) => request.post(`${BASE}/cases/${caseId}/deadlines`, data)
export const updateDeadline = (caseId, id, data) => request.put(`${BASE}/cases/${caseId}/deadlines/${id}`, data)
export const completeDeadline = (caseId, id, result) => request.post(`${BASE}/cases/${caseId}/deadlines/${id}/complete`, { result })
export const deleteDetail = (caseId, type, id) => request.delete(`${BASE}/cases/${caseId}/${type}/${id}`)
export const listActivities = (caseId) => request.get(`${BASE}/cases/${caseId}/activities`)

export const listAttachments = (caseId) => request.get(`${BASE}/cases/${caseId}/attachments`)
export const uploadAttachment = (data) => request.post(`${BASE}/attachments`, data, {
  headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000
})
export const attachmentUrl = (id, mode = 'download') => `/api/v1${BASE}/attachments/${id}/${mode}`
export const fetchAttachment = (id, mode = 'download') => request.get(`${BASE}/attachments/${id}/${mode}`, {
  responseType: 'blob', timeout: 120000
})
export const deleteAttachment = (id) => request.delete(`${BASE}/attachments/${id}`)

export const listAlerts = (params) => request.get(`${BASE}/alerts`, { params })
export const getAlertCounts = () => request.get(`${BASE}/alerts/counts`)
export const getAlertDeliveries = (id) => request.get(`${BASE}/alerts/${id}/deliveries`)
export const startAlert = (id) => request.post(`${BASE}/alerts/${id}/start`)
export const completeAlert = (id, result) => request.post(`${BASE}/alerts/${id}/complete`, { result })
export const closeAlert = (id, result) => request.post(`${BASE}/alerts/${id}/close`, { result })
export const resendAlert = (id) => request.post(`${BASE}/alerts/${id}/resend`)

export const getDashboardStatistics = (params) => request.get(`${BASE}/statistics/dashboard`, { params })
export const getStatusStatistics = (params) => request.get(`${BASE}/statistics/status`, { params })
export const exportCases = (params) => request.get(`${BASE}/exports/cases.xlsx`, {
  params, responseType: 'blob', timeout: 120000
})

export const downloadImportTemplate = () => request.get(`${BASE}/imports/template`, {
  responseType: 'blob', timeout: 120000
})
export const previewImport = (formData) => request.post(`${BASE}/imports/preview`, formData, {
  headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000
})
export const getImportBatch = (id) => request.get(`${BASE}/imports/${id}`)
export const confirmImport = (id, rows) => request.post(`${BASE}/imports/${id}/confirm`, {
  confirmed_warning_rows: rows
}, { timeout: 120000 })
export const downloadImportErrors = (id) => request.get(`${BASE}/imports/${id}/errors.xlsx`, {
  responseType: 'blob', timeout: 120000
})

export const scanAlerts = () => request.post(`${BASE}/admin/scan-alerts`)
export const testDingTalk = () => request.post(`${BASE}/admin/test-dingtalk`)
