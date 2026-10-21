let csrf = ''
export function setCsrf(value: string) { csrf = value }
export async function api<T = any>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch('/api/v1'+path, {...options, credentials:'same-origin', headers:{'Content-Type':'application/json',...(csrf?{'X-CSRF-Token':csrf}:{}),...options.headers}})
  if(!response.ok) {
    let detail = '请求失败，请稍后重试'
    try { const body = await response.json(); detail = typeof body.detail==='string'?body.detail:'参数无效，请检查输入' } catch { /* HTTP body may be empty */ }
    throw new Error(`${response.status} · ${detail}`)
  }
  return response.json()
}
export const fmt = (n: number | null | undefined, digits=0) => n==null?'未知':n.toLocaleString('zh-CN',{maximumFractionDigits:digits>=4&&n!==0&&Math.abs(n)<.0001?8:digits})
export const percent = (n: number | null) => n==null?'—':(n*100).toFixed(1)+'%'
export const date = (n?: number | null) => n?new Date(n*1000).toLocaleString('zh-CN',{hour12:false}):'—'
export const stateLabels: Record<string,string>={queued:'排队中',preparing:'准备中',running:'运行中',evaluating:'验证中',completed:'已完成',failed:'基础设施失败',timeout:'超时',cancelled:'已取消'}
export const isActive=(state:string)=>['queued','preparing','running','evaluating'].includes(state)

// getRandomValues is available on approved local HTTP origins as well as HTTPS.
export const randomId=()=>Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('')
