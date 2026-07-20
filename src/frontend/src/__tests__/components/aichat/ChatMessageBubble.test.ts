import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ChatMessageBubble from '@/components/aichat/ChatMessageBubble.vue'
import type { KBChatMessage } from '@/stores/kbChat'

function mountMessage(message: KBChatMessage) {
  return mount(ChatMessageBubble, {
    props: {
      message,
      saving: false,
      saved: false,
      added: false,
      runningBacktest: false,
      refreshingStatus: false,
      generatingReport: false,
    },
  })
}

describe('ChatMessageBubble', () => {
  it('renders assistant responses as sanitized Markdown', () => {
    const wrapper = mountMessage({
      role: 'assistant',
      content: [
        '## 直接结论',
        '',
        '**贝叶斯网络风险治理**需要持续诊断。',
        '',
        '- 检查模型结构',
        '- 验证采样稳定性',
        '',
        '```python',
        'risk_score = 0.1',
        '```',
      ].join('\n'),
    })

    const content = wrapper.find('.message-content')
    expect(content.find('h2').text()).toBe('直接结论')
    expect(content.find('strong').text()).toBe('贝叶斯网络风险治理')
    expect(content.findAll('li')).toHaveLength(2)
    expect(content.find('pre code').text()).toContain('risk_score = 0.1')
    expect(content.text()).not.toContain('**')
  })

  it('keeps user input as plain text', () => {
    const wrapper = mountMessage({ role: 'user', content: '**不要被渲染**' })

    expect(wrapper.find('.message-content').text()).toBe('**不要被渲染**')
    expect(wrapper.find('.message-content strong').exists()).toBe(false)
  })
})
