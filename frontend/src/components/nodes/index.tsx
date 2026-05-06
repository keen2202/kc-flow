import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import {
  Play,
  StopCircle,
  GitBranch,
  Brain,
  Code,
  Cpu,
} from "lucide-react";

interface NodeData {
  label: string;
  node_type: string;
  [key: string]: unknown;
}

const BaseNode = memo(
  ({
    data,
    icon: Icon,
    color,
    selected,
  }: {
    data: NodeData;
    icon: React.ElementType;
    color: string;
    selected?: boolean;
  }) => (
    <div
      className={`px-4 py-3 rounded-lg border-2 shadow-md min-w-[160px] bg-white transition-all ${
        selected ? "border-blue-500 shadow-lg" : "border-gray-200"
      }`}
    >
      <div className="flex items-center gap-2 mb-1">
        <div className={`p-1.5 rounded ${color}`}>
          <Icon size={14} className="text-white" />
        </div>
        <span className="text-sm font-medium text-gray-800">
          {data.label || data.node_type}
        </span>
      </div>
      <div className="text-xs text-gray-400 mt-1">{data.node_type}</div>
    </div>
  )
);

export const StartNode = memo(({ data, selected }: NodeProps<NodeData>) => (
  <>
    <BaseNode data={data} icon={Play} color="bg-green-500" selected={selected} />
    <Handle type="source" position={Position.Right} className="w-3 h-3" />
  </>
));

export const EndNode = memo(({ data, selected }: NodeProps<NodeData>) => (
  <>
    <Handle type="target" position={Position.Left} className="w-3 h-3" />
    <BaseNode data={data} icon={StopCircle} color="bg-red-500" selected={selected} />
  </>
));

export const ConditionNode = memo(({ data, selected }: NodeProps<NodeData>) => (
  <>
    <Handle type="target" position={Position.Left} className="w-3 h-3" />
    <BaseNode data={data} icon={GitBranch} color="bg-yellow-500" selected={selected} />
    <Handle
      type="source"
      position={Position.Right}
      id="true"
      className="w-3 h-3"
      style={{ top: "35%" }}
    />
    <Handle
      type="source"
      position={Position.Right}
      id="false"
      className="w-3 h-3"
      style={{ top: "65%" }}
    />
  </>
));

export const LLMNode = memo(({ data, selected }: NodeProps<NodeData>) => (
  <>
    <Handle type="target" position={Position.Left} className="w-3 h-3" />
    <BaseNode data={data} icon={Brain} color="bg-purple-500" selected={selected} />
    <Handle type="source" position={Position.Right} className="w-3 h-3" />
  </>
));

export const CodeNode = memo(({ data, selected }: NodeProps<NodeData>) => (
  <>
    <Handle type="target" position={Position.Left} className="w-3 h-3" />
    <BaseNode data={data} icon={Code} color="bg-blue-500" selected={selected} />
    <Handle type="source" position={Position.Right} className="w-3 h-3" />
  </>
));

export const DefaultNode = memo(({ data, selected }: NodeProps<NodeData>) => (
  <>
    <Handle type="target" position={Position.Left} className="w-3 h-3" />
    <BaseNode data={data} icon={Cpu} color="bg-gray-500" selected={selected} />
    <Handle type="source" position={Position.Right} className="w-3 h-3" />
  </>
));
