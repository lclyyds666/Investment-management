import request from './request'

export function listInvoices(params = {}) {
  return request.get('/invoices', { params })
}
export function invoiceStats() {
  return request.get('/invoices/stats')
}

export function invoiceRecordStats(id) {
  return request.get(`/invoices/${id}/stats`)
}

export function createInvoice(data) {
  return request.post('/invoices', data)
}
export function updateInvoice(id, data) {
  return request.put(`/invoices/${id}`, data)
}

export function deleteInvoice(id) {
  return request.delete(`/invoices/${id}`)
}

export function listInvoiceAttachments(id) {
  return request.get(`/invoices/${id}/attachments`)
}

export function uploadInvoiceAttachments(id, files) {
  const form = new FormData()
  files.forEach(file => form.append('files', file))
  return request.post(`/invoices/${id}/attachments`, form)
}

export function downloadInvoiceAttachment(id, attachmentId) {
  return request.get(`/invoices/${id}/attachments/${attachmentId}`, { responseType: 'blob' })
}

export function listInvoiceDetails(id) {
  return request.get(`/invoices/${id}/details`)
}

export function updateInvoiceDetail(id, detailId, data) {
  return request.put(`/invoices/${id}/details/${detailId}`, data)
}

export function submitInvoiceApproval(id, data = {}) {
  return request.post(`/invoices/${id}/approval-form/submit`, data)
}

export function downloadInvoiceDocument(id, documentType) {
  const endpoint = documentType === 'details' ? 'details/print' : 'approval-form/print'
  return request.get(`/invoices/${id}/${endpoint}`, { responseType: 'blob' })
}

export function createInvoiceApprovalForm(id) {
  return request.post(`/invoices/${id}/approval-form`)
}

export function submitInvoiceApprovalForm(id, data = {}) {
  return submitInvoiceApproval(id, data)
}
