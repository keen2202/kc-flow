import { Play, Save, Download, Upload, Undo2, Redo2, Square } from "lucide-react";
import { useWorkflowStore } from "@/stores/workflowStore";
import type { WorkflowDSL } from "@/types";

const API_BASE = "/api/v1";

export function Toolbar() {
  const {
    workflowId,
    workflowName,
    nodes,
    isExecuting,
    undo,
    redo,
    toDSL,
    loadDSL,
    startExecution,
    handleExecutionEvent,
    endExecution,
    setWorkflow,
  } = useWorkflowStore();

  const handleSave = async () => {
    const dsl = toDSL();
    try {
      if (workflowId) {
        await fetch(`${API_BASE}/workflows/${workflowId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ dsl }),
        });
      } else {
        const res = await fetch(`${API_BASE}/workflows`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: workflowName, dsl }),
        });
        const data = await res.json();
        if (data.data?.id) {
          setWorkflow(data.data.id, workflowName, "");
        }
      }
    } catch (err) {
      console.error("Save failed:", err);
    }
  };

  const handleRun = async () => {
    if (!workflowId) {
      await handleSave();
    }
    const id = workflowId || useWorkflowStore.getState().workflowId;
    if (!id) return;

    try {
      startExecution(`exec_${Date.now()}`);

      const res = await fetch(`${API_BASE}/workflows/${id}/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ inputs: {} }),
      });
      const data = await res.json();

      // Simulate events for non-streaming response
      if (data.data?.status) {
        handleExecutionEvent({
          event: "workflow_completed",
          data: data.data,
          timestamp: new Date().toISOString(),
        });
      }
    } catch (err) {
      console.error("Execution failed:", err);
      endExecution();
    }
  };

  const handleExport = () => {
    const dsl = toDSL();
    const blob = new Blob([JSON.stringify(dsl, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${workflowName.replace(/\s+/g, "_")}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleImport = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.onchange = (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (ev) => {
        try {
          const dsl = JSON.parse(ev.target?.result as string) as WorkflowDSL;
          loadDSL(dsl);
        } catch (err) {
          console.error("Invalid JSON:", err);
        }
      };
      reader.readAsText(file);
    };
    input.click();
  };

  return (
    <div className="h-12 bg-white border-b border-gray-200 flex items-center justify-between px-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-gray-800">
          {workflowName}
        </span>
        {nodes.length > 0 && (
          <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
            {nodes.length} nodes
          </span>
        )}
      </div>

      <div className="flex items-center gap-1">
        <button
          onClick={undo}
          className="p-2 rounded hover:bg-gray-100 text-gray-500"
          title="Undo (Ctrl+Z)"
        >
          <Undo2 size={16} />
        </button>
        <button
          onClick={redo}
          className="p-2 rounded hover:bg-gray-100 text-gray-500"
          title="Redo (Ctrl+Y)"
        >
          <Redo2 size={16} />
        </button>

        <div className="w-px h-6 bg-gray-200 mx-1" />

        <button
          onClick={handleImport}
          className="p-2 rounded hover:bg-gray-100 text-gray-500"
          title="Import JSON"
        >
          <Upload size={16} />
        </button>
        <button
          onClick={handleExport}
          className="p-2 rounded hover:bg-gray-100 text-gray-500"
          title="Export JSON"
        >
          <Download size={16} />
        </button>
        <button
          onClick={handleSave}
          className="p-2 rounded hover:bg-gray-100 text-gray-500"
          title="Save"
        >
          <Save size={16} />
        </button>

        <div className="w-px h-6 bg-gray-200 mx-1" />

        {isExecuting ? (
          <button
            onClick={endExecution}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500 text-white rounded text-sm font-medium hover:bg-red-600"
          >
            <Square size={14} />
            停止
          </button>
        ) : (
          <button
            onClick={handleRun}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-green-500 text-white rounded text-sm font-medium hover:bg-green-600"
          >
            <Play size={14} />
            运行
          </button>
        )}
      </div>
    </div>
  );
}
