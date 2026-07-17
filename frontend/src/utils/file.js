// 附件预览 / 下载工具：从带 token 的接口取回 Blob 后在浏览器打开或另存。

/** 触发浏览器下载一个 Blob。 */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || 'download'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

/** 在新标签页预览 Blob（PDF 等浏览器可内嵌渲染）；被拦截则退化为下载。 */
export function previewBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const w = window.open(url, '_blank')
  if (!w) {
    URL.revokeObjectURL(url)
    downloadBlob(blob, filename)
    return
  }
  // 新标签页加载完成前不能立即回收，延时释放
  setTimeout(() => URL.revokeObjectURL(url), 60000)
}
