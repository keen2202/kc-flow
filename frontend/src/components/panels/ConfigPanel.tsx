import { X } from "lucide-react";
import { useWorkflowStore } from "@/stores/workflowStore";

export function ConfigPanel() {
  const { selectedNodeId, nodes, updateNodeData, setSelectedNode } =
    useWorkflowStore();

  if (!selectedNodeId) return null;

  const node = nodes.find((n) => n.id === selectedNodeId);
  if (!node) return null;

  const data = node.data || {};
  const nodeType = (data.node_type as string) || node.type || "unknown";

  return (
    <div className="w-80 bg-white border-l border-gray-200 overflow-y-auto">
      <div className="flex items-center justify-between p-4 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-800">节点配置</h2>
        <button
          onClick={() => setSelectedNode(null)}
          className="p-1 rounded hover:bg-gray-100"
        >
          <X size={16} className="text-gray-400" />
        </button>
      </div>

      <div className="p-4 space-y-4">
        {/* Node ID */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            节点 ID
          </label>
          <div className="text-sm text-gray-800 font-mono bg-gray-50 px-2 py-1 rounded">
            {node.id}
          </div>
        </div>

        {/* Node Type */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            节点类型
          </label>
          <div className="text-sm text-gray-800 bg-gray-50 px-2 py-1 rounded">
            {nodeType}
          </div>
        </div>

        {/* Label */}
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            显示名称
          </label>
          <input
            type="text"
            value={(data.label as string) || ""}
            onChange={(e) =>
              updateNodeData(selectedNodeId, { label: e.target.value })
            }
            className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="节点名称"
          />
        </div>

        {/* Type-specific config */}
        {nodeType === "llm" && <LLMConfig data={data} nodeId={selectedNodeId} />}
        {nodeType === "condition" && (
          <ConditionConfig data={data} nodeId={selectedNodeId} />
        )}
        {nodeType === "code" && <CodeConfig data={data} nodeId={selectedNodeId} />}
        {nodeType === "http_request" && (
          <HTTPConfig data={data} nodeId={selectedNodeId} />
        )}
        {nodeType === "template" && (
          <TemplateConfig data={data} nodeId={selectedNodeId} />
        )}
      </div>
    </div>
  );
}

function LLMConfig({
  data,
  nodeId,
}: {
  data: Record<string, unknown>;
  nodeId: string;
}) {
  const { updateNodeData } = useWorkflowStore();
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">
          模型
        </label>
        <input
          type="text"
          value={(data.model as string) || ""}
          onChange={(e) => updateNodeData(nodeId, { model: e.target.value })}
          className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder="gpt-4o"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">
          提示词模板
        </label>
        <textarea
          value={(data.prompt_template as string) || ""}
          onChange={(e) =>
            updateNodeData(nodeId, { prompt_template: e.target.value })
          }
          className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 h-24 resize-none"
          placeholder="{{node_start.output.query}}"
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            Temperature
          </label>
          <input
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={(data.temperature as number) || 0.7}
            onChange={(e) =>
              updateNodeData(nodeId, { temperature: parseFloat(e.target.value) })
            }
            className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-500 mb-1">
            Max Tokens
          </label>
          <input
            type="number"
            min={1}
            max={128000}
            value={(data.max_tokens as number) || 4096}
            onChange={(e) =>
              updateNodeData(nodeId, { max_tokens: parseInt(e.target.value) })
            }
            className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>
    </div>
  );
}

function ConditionConfig({
  data,
  nodeId,
}: {
  data: Record<string, unknown>;
  nodeId: string;
}) {
  const { updateNodeData } = useWorkflowStore();
  const conditions = (data.conditions as { expression: string; target_node: string }[]) || [];

  return (
    <div className="space-y-3">
      <label className="block text-xs font-medium text-gray-500">条件列表</label>
      {conditions.map((cond, i) => (
        <div key={i} className="bg-gray-50 p-2 rounded space-y-1">
          <input
            type="text"
            value={cond.expression}
            onChange={(e) => {
              const updated = [...conditions];
              updated[i] = { ...updated[i], expression: e.target.value };
              updateNodeData(nodeId, { conditions: updated });
            }}
            className="w-full px-2 py-1 text-xs border border-gray-200 rounded"
            placeholder="{{var}} == 'value'"
          />
        </div>
      ))}
      <button
        onClick={() =>
          updateNodeData(nodeId, {
            conditions: [...conditions, { expression: "", target_node: "" }],
          })
        }
        className="text-xs text-blue-600 hover:text-blue-800"
      >
        + 添加条件
      </button>
    </div>
  );
}

function CodeConfig({
  data,
  nodeId,
}: {
  data: Record<string, unknown>;
  nodeId: string;
}) {
  const { updateNodeData } = useWorkflowStore();
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">
          语言
        </label>
        <select
          value={(data.language as string) || "python"}
          onChange={(e) => updateNodeData(nodeId, { language: e.target.value })}
          className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="python">Python</option>
          <option value="javascript">JavaScript</option>
        </select>
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">
          代码
        </label>
        <textarea
          value={(data.code as string) || ""}
          onChange={(e) => updateNodeData(nodeId, { code: e.target.value })}
          className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 h-40 resize-none font-mono"
          placeholder="def main(inputs):\n    return {'result': inputs}"
        />
      </div>
    </div>
  );
}

function HTTPConfig({
  data,
  nodeId,
}: {
  data: Record<string, unknown>;
  nodeId: string;
}) {
  const { updateNodeData } = useWorkflowStore();
  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">
          URL
        </label>
        <input
          type="text"
          value={(data.url as string) || ""}
          onChange={(e) => updateNodeData(nodeId, { url: e.target.value })}
          className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded"
          placeholder="https://api.example.com/data"
        />
      </div>
      <div>
        <label className="block text-xs font-medium text-gray-500 mb-1">
          方法
        </label>
        <select
          value={(data.method as string) || "GET"}
          onChange={(e) => updateNodeData(nodeId, { method: e.target.value })}
          className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded"
        >
          <option value="GET">GET</option>
          <option value="POST">POST</option>
          <option value="PUT">PUT</option>
          <option value="DELETE">DELETE</option>
        </select>
      </div>
    </div>
  );
}

function TemplateConfig({
  data,
  nodeId,
}: {
  data: Record<string, unknown>;
  nodeId: string;
}) {
  const { updateNodeData } = useWorkflowStore();
  return (
    <div>
      <label className="block text-xs font-medium text-gray-500 mb-1">
        模板内容
      </label>
      <textarea
        value={(data.template as string) || ""}
        onChange={(e) => updateNodeData(nodeId, { template: e.target.value })}
        className="w-full px-2 py-1.5 text-sm border border-gray-200 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 h-32 resize-none font-mono"
        placeholder="Hello {{name}}, welcome!"
      />
    </div>
  );
}
