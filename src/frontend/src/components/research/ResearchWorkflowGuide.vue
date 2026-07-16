<template>
  <section
    class="research-workflow-guide"
    :aria-labelledby="titleId"
  >
    <header class="research-workflow-guide__header">
      <span>{{ kicker }}</span>
      <h2 :id="titleId">
        {{ title }}
      </h2>
    </header>

    <ol class="research-workflow-guide__steps">
      <li
        v-for="(step, index) in steps"
        :key="step.id"
        :class="`research-workflow-guide__step--${step.state}`"
      >
        <span class="research-workflow-guide__index">{{ index + 1 }}</span>
        <div class="research-workflow-guide__copy">
          <div>
            <strong>{{ step.label }}</strong>
            <span>{{ stateLabel(step.state) }}</span>
          </div>
          <p>{{ step.description }}</p>
          <el-button
            v-if="step.action"
            type="primary"
            size="small"
            :aria-label="step.actionLabel || step.label"
            @click="emit('action', step.action)"
          >
            {{ step.actionLabel || step.label }}
          </el-button>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ResearchWorkflowStep, ResearchWorkflowStepState } from '@/types/researchWorkflow'

const props = defineProps<{
  kicker: string
  title: string
  steps: ResearchWorkflowStep[]
  completeLabel: string
  currentLabel: string
  upcomingLabel: string
  attentionLabel: string
}>()

const emit = defineEmits<{
  action: [action: string]
}>()

const titleId = computed(() => `research-workflow-guide-${props.title.replace(/\s+/g, '-').toLowerCase()}`)

function stateLabel(state: ResearchWorkflowStepState): string {
  const labels: Record<ResearchWorkflowStepState, string> = {
    complete: props.completeLabel,
    current: props.currentLabel,
    upcoming: props.upcomingLabel,
    attention: props.attentionLabel,
  }
  return labels[state]
}
</script>

<style scoped>
.research-workflow-guide {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--fill-color-lighter);
}

.research-workflow-guide__header > span {
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 700;
}

.research-workflow-guide__header h2 {
  margin: 4px 0 0;
  color: var(--text-color-primary);
  font-size: 16px;
}

.research-workflow-guide__steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.research-workflow-guide__steps li {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 9px;
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border-color-light);
  border-radius: 8px;
  background: var(--bg-color);
}

.research-workflow-guide__index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 999px;
  background: var(--fill-color);
  color: var(--text-color-secondary);
  font-size: 12px;
  font-weight: 700;
}

.research-workflow-guide__copy {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.research-workflow-guide__copy > div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.research-workflow-guide__copy strong {
  overflow: hidden;
  color: var(--text-color-primary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.research-workflow-guide__copy > div > span {
  flex: none;
  color: var(--text-color-secondary);
  font-size: 11px;
}

.research-workflow-guide__copy p {
  margin: 0;
  color: var(--text-color-secondary);
  font-size: 12px;
  line-height: 1.45;
}

.research-workflow-guide__step--complete .research-workflow-guide__index {
  background: var(--success-surface);
  color: var(--success-text-color);
}

.research-workflow-guide__step--current {
  border-color: var(--info-border-color) !important;
}

.research-workflow-guide__step--current .research-workflow-guide__index {
  background: var(--info-surface);
  color: var(--primary-color);
}

.research-workflow-guide__step--attention {
  border-color: var(--warning-border-color) !important;
}

.research-workflow-guide__step--attention .research-workflow-guide__index {
  background: var(--warning-surface);
  color: var(--warning-text-color);
}

@media (max-width: 980px) {
  .research-workflow-guide__steps {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 540px) {
  .research-workflow-guide {
    padding: 12px;
  }

  .research-workflow-guide__steps {
    grid-template-columns: 1fr;
  }
}
</style>
