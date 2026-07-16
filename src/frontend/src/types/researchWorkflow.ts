export type ResearchWorkflowStepState = 'complete' | 'current' | 'upcoming' | 'attention'

export interface ResearchWorkflowStep {
  id: string
  label: string
  description: string
  state: ResearchWorkflowStepState
  action?: string
  actionLabel?: string
}
