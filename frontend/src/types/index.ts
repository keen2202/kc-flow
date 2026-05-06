// Workflow DSL types matching the Python backend

export type NodeCategory = "control" | "ai" | "data" | "integration";

export type NodeStatus =
  | "pending"
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "skipped"
  | "timeout";

export interface VariableDef {
  name: string;
  type: string;
  required: boolean;
  default?: unknown;
  description: string;
}

export interface NodeConfig {
  node_type: string;
  display_name: string;
  description: string;
  icon: string;
  category: NodeCategory;
  inputs: VariableDef[];
  outputs: VariableDef[];
  config_schema: Record<string, unknown>;
  version: string;
}

export interface WorkflowNode {
  id: string;
  type: string;
  data: Record<string, unknown>;
  position: { x: number; y: number };
}

export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  source_handle?: string;
  target_handle?: string;
  condition_index?: number;
}

export interface WorkflowDSL {
  workflow: {
    id?: string;
    name: string;
    version: string;
    description?: string;
    nodes: WorkflowNode[];
    edges: WorkflowEdge[];
    config?: {
      timeout_seconds?: number;
      max_retries?: number;
      error_strategy?: string;
      checkpoint_enabled?: boolean;
    };
  };
}

export interface ExecutionResult {
  execution_id: string;
  status: string;
  outputs: Record<string, unknown>;
  duration_ms: number;
  total_tokens: number;
}

export interface ExecutionEvent {
  event:
    | "workflow_started"
    | "node_started"
    | "node_completed"
    | "node_skipped"
    | "node_streaming"
    | "workflow_completed"
    | "error"
    | "ping";
  data: Record<string, unknown>;
  timestamp: string;
}
