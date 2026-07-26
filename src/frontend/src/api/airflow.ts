/**
 * Airflow DAG management API client.
 */
import api from '@/api'

export interface AirflowDAG {
  dag_id: string
  description?: string
  schedule_interval?: string
  is_paused: boolean
  is_active: boolean
  tags?: { name: string }[]
}

export interface AirflowDAGRun {
  dag_run_id: string
  dag_id: string
  state: string
  start_date?: string
  end_date?: string
  conf?: Record<string, unknown>
}

export interface AirflowTaskInstance {
  task_id: string
  dag_id: string
  dag_run_id: string
  state: string
  start_date?: string
  end_date?: string
  duration?: number
  try_number: number
  max_tries: number
}

export interface OrchestrationStatus {
  type: string
  connected?: boolean
  running?: boolean
  job_count?: number
  api_url?: string
  backend_type?: string
}

export const airflowApi = {
  /** Get orchestration backend status */
  getStatus(): Promise<OrchestrationStatus> {
    return api.get<OrchestrationStatus>('/data/airflow/orchestration/status')
  },

  /** List all DAGs */
  listDags(limit = 100, offset = 0): Promise<{ dags: AirflowDAG[]; total_entries: number }> {
    return api.get('/data/airflow/dags', { params: { limit, offset } })
  },

  /** Get DAG details */
  getDag(dagId: string): Promise<AirflowDAG> {
    return api.get(`/data/airflow/dags/${dagId}`)
  },

  /** Trigger a DAG run */
  triggerDag(dagId: string, conf?: Record<string, unknown>): Promise<AirflowDAGRun> {
    return api.post(`/data/airflow/dags/${dagId}/trigger`, conf ? { conf } : undefined)
  },

  /** Pause or unpause a DAG */
  togglePause(dagId: string, isPaused: boolean): Promise<AirflowDAG> {
    return api.patch(`/data/airflow/dags/${dagId}/pause`, undefined, {
      params: { is_paused: isPaused },
    })
  },

  /** List DAG runs */
  listDagRuns(dagId: string, limit = 25): Promise<{ dag_runs: AirflowDAGRun[]; total_entries: number }> {
    return api.get(`/data/airflow/dags/${dagId}/runs`, { params: { limit } })
  },

  /** Get task instances for a DAG run */
  getTaskInstances(dagId: string, dagRunId: string): Promise<{ task_instances: AirflowTaskInstance[] }> {
    return api.get(`/data/airflow/dags/${dagId}/runs/${dagRunId}/tasks`)
  },

  /** Get task log */
  getTaskLog(dagId: string, dagRunId: string, taskId: string, tryNumber = 1): Promise<{ log: string }> {
    return api.get(`/data/airflow/dags/${dagId}/runs/${dagRunId}/tasks/${taskId}/logs`, {
      params: { try_number: tryNumber },
    })
  },
}
