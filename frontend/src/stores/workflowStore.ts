import { create } from "zustand";
import {
  type Edge,
  type Node,
  type OnNodesChange,
  type OnEdgesChange,
  type Connection,
  applyNodeChanges,
  applyEdgeChanges,
  addEdge,
} from "reactflow";
import type { ExecutionEvent, NodeStatus, WorkflowDSL } from "@/types";

interface NodeExecutionState {
  status: NodeStatus;
  duration_ms?: number;
  error?: string;
}

interface WorkflowState {
  // Workflow metadata
  workflowId: string | null;
  workflowName: string;
  workflowDescription: string;

  // Canvas state
  nodes: Node[];
  edges: Edge[];

  // Execution state
  executionId: string | null;
  nodeStates: Record<string, NodeExecutionState>;
  isExecuting: boolean;
  streamingText: Record<string, string>;

  // Selected node for config panel
  selectedNodeId: string | null;

  // Actions
  onNodesChange: OnNodesChange;
  onEdgesChange: OnEdgesChange;
  onConnect: (connection: Connection) => void;
  addNode: (node: Node) => void;
  removeNode: (nodeId: string) => void;
  updateNodeData: (nodeId: string, data: Record<string, unknown>) => void;
  setSelectedNode: (nodeId: string | null) => void;
  setWorkflow: (id: string, name: string, description: string) => void;
  loadDSL: (dsl: WorkflowDSL) => void;
  toDSL: () => WorkflowDSL;

  // Execution actions
  startExecution: (executionId: string) => void;
  handleExecutionEvent: (event: ExecutionEvent) => void;
  endExecution: () => void;

  // Undo/redo
  history: { nodes: Node[]; edges: Edge[] }[];
  historyIndex: number;
  pushHistory: () => void;
  undo: () => void;
  redo: () => void;
}

export const useWorkflowStore = create<WorkflowState>((set, get) => ({
  // Initial state
  workflowId: null,
  workflowName: "Untitled Workflow",
  workflowDescription: "",
  nodes: [],
  edges: [],
  executionId: null,
  nodeStates: {},
  isExecuting: false,
  streamingText: {},
  selectedNodeId: null,
  history: [],
  historyIndex: -1,

  // Canvas callbacks
  onNodesChange: (changes) => {
    set({ nodes: applyNodeChanges(changes, get().nodes) });
  },
  onEdgesChange: (changes) => {
    set({ edges: applyEdgeChanges(changes, get().edges) });
  },
  onConnect: (connection) => {
    const edge = {
      ...connection,
      id: `e_${connection.source}_${connection.target}`,
      type: "smoothstep",
    };
    set({ edges: addEdge(edge, get().edges) });
    get().pushHistory();
  },

  addNode: (node) => {
    set({ nodes: [...get().nodes, node] });
    get().pushHistory();
  },

  removeNode: (nodeId) => {
    set({
      nodes: get().nodes.filter((n) => n.id !== nodeId),
      edges: get().edges.filter(
        (e) => e.source !== nodeId && e.target !== nodeId
      ),
      selectedNodeId:
        get().selectedNodeId === nodeId ? null : get().selectedNodeId,
    });
    get().pushHistory();
  },

  updateNodeData: (nodeId, data) => {
    set({
      nodes: get().nodes.map((n) =>
        n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n
      ),
    });
  },

  setSelectedNode: (nodeId) => set({ selectedNodeId: nodeId }),

  setWorkflow: (id, name, description) =>
    set({ workflowId: id, workflowName: name, workflowDescription: description }),

  loadDSL: (dsl) => {
    const nodes: Node[] = dsl.workflow.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      position: n.position,
      data: n.data,
    }));
    const edges: Edge[] = dsl.workflow.edges.map((e) => ({
      id: e.id || `e_${e.source}_${e.target}`,
      source: e.source,
      target: e.target,
      sourceHandle: e.source_handle,
      targetHandle: e.target_handle,
      type: "smoothstep",
    }));
    set({
      nodes,
      edges,
      workflowName: dsl.workflow.name,
      workflowDescription: dsl.workflow.description || "",
    });
  },

  toDSL: () => {
    const { nodes, edges, workflowName, workflowDescription } = get();
    return {
      workflow: {
        name: workflowName,
        version: "0.1.0",
        description: workflowDescription,
        nodes: nodes.map((n) => ({
          id: n.id,
          type: n.type || "code",
          data: n.data || {},
          position: n.position,
        })),
        edges: edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          source_handle: e.sourceHandle || "output",
          target_handle: e.targetHandle || "input",
        })),
      },
    };
  },

  // Execution
  startExecution: (executionId) => {
    set({
      executionId,
      isExecuting: true,
      nodeStates: {},
      streamingText: {},
    });
  },

  handleExecutionEvent: (event) => {
    const { nodeStates, streamingText } = get();

    switch (event.event) {
      case "node_started": {
        const nodeId = event.data.node_id as string;
        set({
          nodeStates: {
            ...nodeStates,
            [nodeId]: { status: "running" },
          },
        });
        break;
      }
      case "node_completed": {
        const nodeId = event.data.node_id as string;
        set({
          nodeStates: {
            ...nodeStates,
            [nodeId]: {
              status: (event.data.status as NodeStatus) || "succeeded",
              duration_ms: event.data.duration_ms as number,
            },
          },
        });
        break;
      }
      case "node_skipped": {
        const nodeId = event.data.node_id as string;
        set({
          nodeStates: {
            ...nodeStates,
            [nodeId]: { status: "skipped" },
          },
        });
        break;
      }
      case "node_streaming": {
        const nodeId = event.data.node_id as string;
        const chunk = (event.data.text as string) || "";
        set({
          streamingText: {
            ...streamingText,
            [nodeId]: (streamingText[nodeId] || "") + chunk,
          },
        });
        break;
      }
      case "workflow_completed":
      case "error":
        set({ isExecuting: false });
        break;
    }
  },

  endExecution: () =>
    set({ isExecuting: false, executionId: null }),

  // Undo/Redo
  pushHistory: () => {
    const { nodes, edges, history, historyIndex } = get();
    const newHistory = history.slice(0, historyIndex + 1);
    newHistory.push({ nodes: [...nodes], edges: [...edges] });
    // Limit history to 50 entries
    if (newHistory.length > 50) newHistory.shift();
    set({ history: newHistory, historyIndex: newHistory.length - 1 });
  },

  undo: () => {
    const { history, historyIndex } = get();
    if (historyIndex > 0) {
      const prev = history[historyIndex - 1];
      set({
        nodes: prev.nodes,
        edges: prev.edges,
        historyIndex: historyIndex - 1,
      });
    }
  },

  redo: () => {
    const { history, historyIndex } = get();
    if (historyIndex < history.length - 1) {
      const next = history[historyIndex + 1];
      set({
        nodes: next.nodes,
        edges: next.edges,
        historyIndex: historyIndex + 1,
      });
    }
  },
}));
