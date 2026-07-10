import request from './request'

export function listCustomers() {
  return request.get('/customers')
}
export function getCustomer(id) {
  return request.get(`/customers/${id}`)
}
export function createCustomer(data) {
  return request.post('/customers', data)
}
export function updateCustomer(id, data) {
  return request.put(`/customers/${id}`, data)
}
export function deleteCustomer(id) {
  return request.delete(`/customers/${id}`)
}
