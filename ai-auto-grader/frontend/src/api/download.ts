import request from './request'

/** 触发浏览器下载：把 blob 响应保存为文件。 */
export function saveBlob(data: BlobPart, filename: string, mime = 'application/octet-stream') {
  const url = URL.createObjectURL(new Blob([data], { type: mime }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

/** 从 Content-Disposition 中解析文件名（兼容 filename* 与 filename）。 */
export function filenameFrom(disposition: string | undefined, fallback: string): string {
  if (!disposition) return fallback
  const star = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (star) {
    try {
      return decodeURIComponent(star[1])
    } catch {
      return star[1]
    }
  }
  const plain = disposition.match(/filename="?([^";]+)"?/i)
  return plain ? plain[1] : fallback
}

/** 下载接口返回的二进制文件，使用服务端文件名（若有）。 */
export async function downloadBlob(
  url: string,
  fallbackName: string,
  params?: Record<string, any>,
) {
  const res = await request.get(url, { params, responseType: 'blob' })
  const filename = filenameFrom(String(res.headers['content-disposition'] || ''), fallbackName)
  saveBlob(res.data, filename, String(res.headers['content-type'] || 'application/octet-stream'))
  return filename
}