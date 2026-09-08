import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import RunHistoryPanel from '@/components/aiResearch/RunHistoryPanel.vue'
import TaskEventTimeline from '@/components/aiResearch/TaskEventTimeline.vue'
import type { AiResearchV2Task, AiResearchV2TaskEvent } from '@/types/aiResearchV2'

const task: AiResearchV2Task = {
  id: 'task-1',
  run_id: 'run-1',
  status: 'RUNNING',
  stage_cursor: 'GENERATE',
  error_code: null,
  trace_id: 'trace-1',
  attempt_count: 1,
  created_at: '2026-09-05T00:00:00Z',
}

describe('trusted research task observability panels', () => {
  it('renders the safe task history summary and emits the selected task', async () => {
    const wrapper = mount(RunHistoryPanel, {
      props: {
        tasks: [task],
        selectedTaskId: 'task-1',
        nextCursor: 'opaque-next-page',
      },
    })

    expect(wrapper.text()).toContain('task-1')
    expect(wrapper.text()).toContain('run-1')
    expect(wrapper.get('button[aria-current="true"]').attributes('aria-label')).toContain('task-1')
    await wrapper.get('button[aria-current="true"]').trigger('click')
    await wrapper.get('[data-test="trusted-research-history-load-more"]').trigger('click')

    expect(wrapper.emitted('select')?.[0]).toEqual([task])
    expect(wrapper.emitted('load-more')).toHaveLength(1)
  })

  it('renders only the event allowlist and excludes untyped controlled content', () => {
    const event = {
      id: 'event-1',
      task_id: 'task-1',
      run_id: 'run-1',
      sequence_no: 1,
      event_type: 'STAGE_STARTED',
      stage: 'GENERATE',
      status: 'RUNNING',
      error_code: null,
      stage_attempt_id: 'attempt-1',
      trace_id: 'trace-1',
      created_at: '2026-09-05T00:01:00Z',
      raw_prompt: 'must-not-render-controlled-prompt',
    } as AiResearchV2TaskEvent & { raw_prompt: string }
    const wrapper = mount(TaskEventTimeline, {
      props: { taskId: 'task-1', events: [event] },
    })

    expect(wrapper.text()).toContain('STAGE_STARTED')
    expect(wrapper.text()).toContain('GENERATE')
    expect(wrapper.text()).toContain('trace-1')
    expect(wrapper.html()).not.toContain('must-not-render-controlled-prompt')
  })
})
