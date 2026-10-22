import React,{useRef,useState} from 'react'
import {api,randomId} from './api'

type Item=Record<string,any>
export function UpstreamModelImport({providers,models,changed,close}:{providers:Item[],models:Item[],changed:()=>void,close:()=>void}) {
 const identities=useRef(new Map<string,string>())
 const [provider,setProvider]=useState(''),[items,setItems]=useState<{id:string}[]>([]),[selected,setSelected]=useState<string[]>([]),[query,setQuery]=useState(''),[loaded,setLoaded]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[enabled,setEnabled]=useState(false),[created,setCreated]=useState<string[]>([])
 const configured=(id:string)=>created.includes(id)||models.some(m=>m.provider_id===provider&&m.model_id===id&&!m.archived)
 const available=items.filter(m=>!configured(m.id)),filtered=items.filter(m=>m.id.toLowerCase().includes(query.toLowerCase()))
 const load=async()=>{setBusy(true);setError('');setNotice('');setItems([]);setSelected([]);setLoaded(false);try{const value=await api('/manage/providers/'+encodeURIComponent(provider)+'/discover-models',{method:'POST'});setItems(value.items);setLoaded(true);setNotice(`读取到 ${value.items.length} 个模型${value.truncated?'（仅显示前 500 个）':''}，未执行推理。`)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 const save=async()=>{
  setBusy(true);setError('');const saved:string[]=[],failed:string[]=[]
  for(const model of selected){
   const slug=model.replace(/[^a-zA-Z0-9_.-]/g,'-').slice(0,30),prefix=provider.slice(0,20),binding=JSON.stringify([provider,model])
   if(!identities.current.has(binding))identities.current.set(binding,`up-${prefix}-${slug}-${randomId().slice(0,12)}`)
   try{await api('/manage/models',{method:'POST',body:JSON.stringify({id:identities.current.get(binding),display_name:model,provider_id:provider,model_id:model,upstream_id:provider,enabled,data_origin:'unverified',request_timeout:60,max_output_tokens:2048,max_total_tokens:30000,max_agent_steps:12,max_model_calls:15,max_evaluation_duration:300,pricing:null})});saved.push(model)}catch(e){failed.push(model);setError((e as Error).message)}
  }
  setCreated(old=>[...old,...saved]);setSelected(failed);setNotice(`已添加 ${saved.length} 个模型配置${failed.length?`，${failed.length} 个失败，可重试`:''}。${enabled?'新任务立即可选。':'默认停用，请在模型配置中检查后启用。'}`);if(saved.length)changed();setBusy(false)
 }
 return <section className="panel" aria-label="从上游选择模型"><div className="panel-title"><h3>从上游选择模型</h3><button disabled={busy} onClick={close}>关闭模型导入</button></div>
  <p className="muted">只读取提供商模型列表；密钥保留在服务端。选择后才创建独立模型配置，不执行推理。</p>
  {error&&<div role="alert" className="error">{error}</div>}{notice&&<div role="status" className="notice">{notice}</div>}
  <div className="form-grid"><label>上游模型提供商<select aria-label="上游模型提供商" value={provider} disabled={busy} onChange={e=>{setProvider(e.target.value);setItems([]);setSelected([]);setCreated([]);setLoaded(false);setError('');setNotice('')}}><option value="">选择提供商</option>{providers.filter(p=>p.enabled&&!p.archived&&!p.credential?.revoked).map(p=><option key={p.id} value={p.id}>{p.display_name} ({p.id})</option>)}</select></label><div className="actions"><button disabled={!provider||busy} onClick={load}>{busy?'处理中…':'读取上游模型列表'}</button></div></div>
  {loaded&&<><label>搜索上游模型<input aria-label="搜索上游模型" value={query} disabled={busy} onChange={e=>setQuery(e.target.value)} placeholder="输入模型 ID"/></label><p>已选择 {selected.length} / 20 · {available.length} 个尚未配置</p><div className="actions"><button disabled={busy||!available.length} onClick={()=>setSelected(filtered.filter(m=>!configured(m.id)).slice(0,20).map(m=>m.id))}>选择当前结果（最多 20 个）</button><button disabled={busy||!selected.length} onClick={()=>setSelected([])}>清空选择</button></div><div className="task-picker">{filtered.map(m=><label className="check" key={m.id}><input aria-label={'选择上游模型 '+m.id} type="checkbox" checked={selected.includes(m.id)} disabled={busy||configured(m.id)||(!selected.includes(m.id)&&selected.length>=20)} onChange={()=>setSelected(selected.includes(m.id)?selected.filter(x=>x!==m.id):[...selected,m.id])}/><span>{m.id}{configured(m.id)&&<small>已配置</small>}</span></label>)}</div>{!items.length&&<p>提供商未返回可用模型 ID。可继续手动新建模型。</p>}{!!items.length&&!filtered.length&&<p>没有匹配的上游模型。</p>}
   <div className="notice">默认预算：请求 60 秒、单次运行 300 秒、12 步 / 15 次请求、输出 2048 / 总量 30000 token。价格未知，执行来源与上游身份默认未验证。导入后可逐个编辑推理参数、预算和价格。</div>
   <label className="check"><input aria-label="导入后启用模型" type="checkbox" checked={enabled} disabled={busy} onChange={e=>setEnabled(e.target.checked)}/>导入后启用模型（不会执行推理）</label><button className="primary" disabled={busy||!selected.length} onClick={save}>添加所选模型（{selected.length}）</button></>}
 </section>
}
