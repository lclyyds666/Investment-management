import request from './request'

export function listInvoices() {
  return request.get('/invoices')
}
export function invoiceStats() {
  return request.get('/invoices/stats')
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
