import request from './request'

/** 法规知识库列表 */
export function listKnowledge() {
  return request.get('/knowledge')
}

/** 上传法规文件（超管）：pdf/docx/xlsx */
export function uploadKnowledge(file, title, category) {
  const form = new FormData()
  form.append('file', file)
  form.append('title', title || '')
  form.append('category', category || '法律规范')
  return request.post('/knowledge', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000
  })
}

/** 删除法规文件（超管） */
export function deleteKnowledge(id) {
  return request.delete(`/knowledge/${id}`)
}
