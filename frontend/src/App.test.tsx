import React from 'react'
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react'
import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest'
import {App,Tasks} from './main'
import {fmt,percent} from './api'
let logged=false
const model={id:'fixture-profile',model_id:'test-model',upstream_id:'channel-test',endpoint_identity:'abcd',data_origin:'local_stub',upstream_verified:false,capabilities:{reasoning_effort:false},max_output_tokens:100,max_model_calls:3,max_agent_steps:2,request_timeout:5}
const task={id:'intervals-001',benchmark:'local',dataset_version:'1',issue:'Fix touching ranges',base_commit:'aaa'}
const calls:{path:string,options:any}[]=[]
beforeEach(()=>{logged=false;calls.length=0;localStorage.clear();vi.stubGlobal('fetch',vi.fn(async(path:string,options:any={})=>{calls.push({path,options});let status=200,body:any={items:[]};if(path==='/api/v1/session'){if(options.method==='POST'){logged=true;body={csrf_token:'dummy-csrf'}}else if(options.method==='DELETE'){logged=false;body={}}else if(!logged){status=401;body={detail:'authentication required'}}else body={csrf_token:'dummy-csrf'}}else if(path==='/api/v1/models')body={items:[model]};else if(path==='/api/v1/tasks')body={items:[task]};else if(path==='/api/v1/overview')body={total_runs:0,states:{},legacy_or_unattributed_runs:0,trusted_metrics:{resolved:0,valid_evaluations:0,repair_failures:0,infrastructure_errors:0,unknown_cost_attempts:0},operations:{worker_ready:false,queue_depth:0}};else if(path.startsWith('/api/v1/comparison'))body={groups:[],excluded:{}};else if(path.startsWith('/api/v1/runs?'))body={items:[],total:0};else if(path==='/api/v1/batches'&&options.method==='POST')body={id:'batch1',name:'Test experiment',total:1,terminal:0,attempts:[],configuration:{reserved_requests:15},progress:{}};return new Response(JSON.stringify(body),{status})}))})
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
async function login(){render(<App/>);await screen.findByText('管理员登录');fireEvent.change(screen.getByLabelText('控制台密码'),{target:{value:'dummy-password'}});fireEvent.click(screen.getByText('安全登录 →'));await screen.findByText('让代码执行，验证模型能力。')}
describe('dashboard',()=>{
 it('requires login and displays actual empty state',async()=>{await login();expect(await screen.findByText('还没有可信对比数据')).toBeInTheDocument();expect(screen.getByText('工作进程未就绪')).toBeInTheDocument();expect(localStorage.getItem('swe-theme')).toBe('light');expect(JSON.stringify(localStorage)).not.toContain('dummy-password')})
 it('shows model metadata without API key field',async()=>{await login();fireEvent.click(screen.getByRole('button',{name:'模型配置'}));expect(await screen.findByText('test-model')).toBeInTheDocument();expect(screen.getByText('abcd')).toBeInTheDocument();expect(screen.queryByText('api_key')).not.toBeInTheDocument()})
 it('filters runs and handles pagination empty state',async()=>{await login();fireEvent.click(screen.getByRole('button',{name:'评测记录'}));await screen.findByText('没有符合条件的评测');fireEvent.change(screen.getByLabelText('模型筛选'),{target:{value:'fixture-profile'}});await waitFor(()=>expect(calls.some(c=>c.path.includes('model_profile_id=fixture-profile'))).toBe(true));expect(screen.getByText('下一页')).toBeDisabled()})
 it('submits bounded batch with CSRF and traceable identity',async()=>{await login();fireEvent.click(screen.getAllByRole('button',{name:/批量实验/}).find(b=>b.closest('aside'))!);fireEvent.click(screen.getByText('＋ 新建批量实验'));fireEvent.change(screen.getByPlaceholderText('例如：十月编码能力对比'),{target:{value:'Test experiment'}});fireEvent.click(screen.getByLabelText('intervals-001 · v1'));fireEvent.click(screen.getByLabelText('fixture-profile / channel-test'));fireEvent.click(screen.getByText('确认创建实验'));await waitFor(()=>expect(calls.some(c=>c.path==='/api/v1/batches'&&c.options.method==='POST')).toBe(true));const call=calls.find(c=>c.path==='/api/v1/batches'&&c.options.method==='POST')!;expect(call.options.headers['X-CSRF-Token']).toBe('dummy-csrf');expect(JSON.parse(call.options.body).limits.requests).toBe(15);expect(JSON.parse(call.options.body).idempotency_key).toBeTruthy()})
 it('unknown numbers are never shown as zero',()=>{expect(fmt(null)).toBe('未知');expect(percent(null)).toBe('—');expect(fmt(0)).toBe('0')})
})

it.each([2,null])('run detail displays total cost and unknown state: %s',async(cost)=>{
 await login();const original=globalThis.fetch
 const run={id:'cost-detail',state:'completed',model,task,created_at:100,metrics:{resolved:true,assertions_passed:10,assertions_expected:10,model_requests:1,agent_steps:1,wall_seconds:10,cost,currency:cost==null?null:'USD',execution_metadata:{}}}
 vi.stubGlobal('fetch',vi.fn(async(path:string,options:any={})=>{
  if(path.startsWith('/api/v1/runs?'))return new Response(JSON.stringify({items:[run],total:1}))
  if(path==='/api/v1/runs/cost-detail')return new Response(JSON.stringify(run))
  if(path.includes('/logs'))return new Response(JSON.stringify({items:[]}))
  if(path.endsWith('/patch'))return new Response('')
  return original(path,options)
 }))
 fireEvent.click(screen.getByRole('button',{name:'评测记录'}));fireEvent.click(await screen.findByText('cost-detai'))
 expect(await screen.findByText('总费用')).toBeInTheDocument()
 expect(screen.getByText(cost==null?'费用未知 / 未提供价格或用量':'2.0000 USD')).toBeInTheDocument()
})

it('health renders heartbeat completion and infrastructure errors without invented probes',async()=>{
 await login();const original=globalThis.fetch
 vi.stubGlobal('fetch',vi.fn(async(path:string,options:any={})=>path==='/api/v1/system'?new Response(JSON.stringify({api:'ready',database:'ready',worker_ready:false,worker_lease_status:'expired',lease_valid:false,last_worker_heartbeat_at:100,last_completed_evaluation:{id:'completed-evaluation',finished_at:110},recent_infrastructure_errors:[{id:'failed-evaluation',state:'timeout',error:'evaluation_time_limit_exceeded',finished_at:120}],orphan_cleanup:{status:'unknown'},queue_depth:0,events:[],docker:'unknown',upstream:'not_probed'})):original(path,options)))
 fireEvent.click(screen.getByRole('button',{name:'系统健康'}));expect(await screen.findByText('最近 Worker 心跳')).toBeInTheDocument();expect(screen.getByText('completed-evaluation')).toBeInTheDocument();expect(screen.getByText('evaluation_time_limit_exceeded')).toBeInTheDocument()
})

it('official catalogue separates imported metadata from executable readiness and filters instances',async()=>{
 const official={id:'swv-instance',benchmark_type:'official',benchmark:'SWE-bench/SWE-bench_Verified',dataset_version:'pinned-revision',instance_id:'sympy__sympy-20590',repo:'sympy/sympy',issue:'Public issue only',subset:'curated-20-v1',environment_ready:false,validation_status:'imported',grading_protocol:'swebench-official-v5'}
 render(<Tasks items={[official]}/>);expect(screen.getByText('sympy__sympy-20590')).toBeInTheDocument();expect(screen.getByText('未验证')).toBeInTheDocument()
 fireEvent.change(screen.getByLabelText('Instance ID'),{target:{value:'does-not-exist'}})
 expect(screen.getByText('没有符合条件的任务')).toBeInTheDocument()
 expect(document.body.textContent).not.toContain('GOLD_PRIVATE_CANARY')
})
