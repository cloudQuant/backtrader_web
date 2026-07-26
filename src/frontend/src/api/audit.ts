/**
 * Audit API client for event reporting and record querying.
 */
import api from '@/api'

export interface OperationEvent {
  event_type: string
  event_target?: string | null
  page_path: string
  event_data?: Record<string, unknown> | null
  client_timestamp: string
  session_id?: string | null
}

export interface AuditEventBatchResponse {
  persisted: number
  total: number
}

export interface AuditQueryParams {
  user_id?: string
  event_type?: string
  start_time?: string
  end_time?: string
  page?: number
  page_size?: number
}

export interface AuditRecord {
  id: string
  user_id: string
  session_id: string | null
  event_type: string
  event_target: string | null
  page_path: string
  event_data: Record<string, unknown> | null
  client_timestamp: string
  server_timestamp: string
  client_ip: string | null
}

export interface AuditQueryResponse {
  items: AuditRecord[]
  total_count: number
  current_page: number
  total_pages: number
}

/**
 * Post a batch of audit events to the backend.
 */
export async function postAuditEvents(
  events: OperationEvent[],
): Promise<AuditEventBatchResponse> {
  return api.post<AuditEventBatchResponse>('/audit/events', { events })
}

/**
 * Query audit records (admin only).
 */
export async function getAuditRecords(
  params: AuditQueryParams,
): Promise<AuditQueryResponse> {
  return api.get<AuditQueryResponse>('/audit/records', { params })
}
