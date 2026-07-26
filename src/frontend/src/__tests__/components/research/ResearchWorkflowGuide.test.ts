import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ResearchWorkflowGuide from '@/components/research/ResearchWorkflowGuide.vue'
import { elStubs } from '@/test/stubs'

describe('ResearchWorkflowGuide', () => {
  it('renders workflow state and emits the selected next action', async () => {
    const wrapper = mount(ResearchWorkflowGuide, {
      props: {
        kicker: 'Research flow',
        title: 'From idea to result',
        completeLabel: 'Done',
        currentLabel: 'Do now',
        upcomingLabel: 'Later',
        attentionLabel: 'Review',
        steps: [
          { id: 'create', label: 'Create', description: 'Create a workspace', state: 'current', action: 'create', actionLabel: 'Start' },
          { id: 'review', label: 'Review', description: 'Read the outcome', state: 'upcoming' },
        ],
      },
      global: { stubs: elStubs },
    })

    expect(wrapper.findAll('.research-workflow-guide__steps li')).toHaveLength(2)
    expect(wrapper.text()).toContain('Do now')
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('action')).toEqual([['create']])
  })
})
