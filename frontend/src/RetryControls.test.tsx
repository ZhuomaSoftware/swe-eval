import React from 'react'
import {render,screen,fireEvent} from '@testing-library/react'
import {describe,it,expect,vi} from 'vitest'
import {RetryControls,RetryHistory,defaultApiRetry,defaultRunRecovery} from './RetryControls'
describe('retry controls and history',()=>{
 it('shows bounded defaults and distinct attempt semantics',()=>{const change=vi.fn();render(<RetryControls api={defaultApiRetry} recovery={defaultRunRecovery} changeApi={change} changeRecovery={change}/>);expect(screen.getByLabelText('启用 API 请求重试')).toBeChecked();expect(screen.getByLabelText('启用自动失败运行恢复（每个原始尝试最多 1 次）')).not.toBeChecked();expect(screen.getByText(/独立尝试 ≠ API 请求重试/)).toBeVisible();fireEvent.click(screen.getByLabelText('启用 API 请求重试'));expect(change).toHaveBeenCalledWith({...defaultApiRetry,enabled:false})})
 it('shows quota stop and uncertainty without repair success claim',()=>{render(<RetryHistory run={{metrics:{model_requests:1,http_attempts:1,http_retries:0,provider_outcome:'failed',last_provider_error:{category:'quota_exhausted',http_status:429},billing_uncertain:true}}}/>);expect(screen.getByText('配额不足，停止重试')).toBeVisible();expect(screen.getByText('是，未知用量不可当作零')).toBeVisible()})
 it('shows recovery parent and child separately',()=>{render(<RetryHistory run={{parent_id:'parent-123',metrics:{http_attempts:3,http_retries:2,provider_outcome:'succeeded'},retry:{children:[{child_id:'child-123',state:'completed'}]}}}/>);expect(screen.getByText('parent-123')).toBeVisible();expect(screen.getByText('child-123')).toBeVisible();expect(screen.getByText('API 响应已收到（修复结果由裁判确定）')).toBeVisible()})
})
