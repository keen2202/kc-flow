import { ReactFlowProvider } from "reactflow";
import { WorkflowCanvas } from "@/components/canvas/WorkflowCanvas";
import { NodePalette } from "@/components/canvas/NodePalette";
import { ConfigPanel } from "@/components/panels/ConfigPanel";
import { Toolbar } from "@/components/canvas/Toolbar";
import { MarketplaceView } from "@/components/marketplace/MarketplaceView";
import { useWorkflowStore } from "@/stores/workflowStore";
import { useEffect, useState } from "react";
import { GitBranch, Store } from "lucide-react";

type Tab = "workflow" | "marketplace";

export default function App() {
  const { selectedNodeId, undo, redo } = useWorkflowStore();
  const [tab, setTab] = useState<Tab>("workflow");

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey) {
        if (e.key === "z" && !e.shiftKey) {
          e.preventDefault();
          undo();
        } else if ((e.key === "z" && e.shiftKey) || e.key === "y") {
          e.preventDefault();
          redo();
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [undo, redo]);

  return (
    <ReactFlowProvider>
      <div className="flex flex-col h-screen bg-gray-50">
        {/* Tab navigation */}
        <div className="flex items-center border-b bg-white px-4">
          <button
            onClick={() => setTab("workflow")}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              tab === "workflow"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            <GitBranch className="w-4 h-4" />
            Workflow
          </button>
          <button
            onClick={() => setTab("marketplace")}
            className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              tab === "marketplace"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            <Store className="w-4 h-4" />
            Marketplace
          </button>
        </div>

        {tab === "workflow" ? (
          <>
            <Toolbar />
            <div className="flex flex-1 overflow-hidden">
              <NodePalette />
              <div className="flex-1">
                <WorkflowCanvas />
              </div>
              {selectedNodeId && <ConfigPanel />}
            </div>
          </>
        ) : (
          <MarketplaceView />
        )}
      </div>
    </ReactFlowProvider>
  );
}
