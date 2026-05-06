import {
  Play,
  StopCircle,
  GitBranch,
  Repeat,
  Columns,
  Brain,
  Database,
  Tags,
  Filter,
  Bot,
  Users,
  Code,
  Globe,
  FileText,
  Shuffle,
  File,
  Link,
  Puzzle,
  Clock,
} from "lucide-react";
import type { NodeCategory } from "@/types";

interface PaletteItem {
  type: string;
  label: string;
  icon: React.ElementType;
  category: NodeCategory;
}

const PALETTE_ITEMS: PaletteItem[] = [
  // Control
  { type: "start", label: "开始", icon: Play, category: "control" },
  { type: "end", label: "结束", icon: StopCircle, category: "control" },
  { type: "condition", label: "条件分支", icon: GitBranch, category: "control" },
  { type: "loop", label: "循环", icon: Repeat, category: "control" },
  { type: "parallel", label: "并行分支", icon: Columns, category: "control" },
  // AI
  { type: "llm", label: "大模型推理", icon: Brain, category: "ai" },
  { type: "knowledge_retrieval", label: "知识库检索", icon: Database, category: "ai" },
  { type: "question_classifier", label: "意图分类", icon: Tags, category: "ai" },
  { type: "parameter_extractor", label: "参数提取", icon: Filter, category: "ai" },
  { type: "agent", label: "自主Agent", icon: Bot, category: "ai" },
  { type: "multi_agent", label: "多Agent协同", icon: Users, category: "ai" },
  // Data
  { type: "code", label: "代码执行", icon: Code, category: "data" },
  { type: "http_request", label: "HTTP请求", icon: Globe, category: "data" },
  { type: "template", label: "模板转换", icon: FileText, category: "data" },
  { type: "data_transform", label: "数据转换", icon: Shuffle, category: "data" },
  { type: "document_parser", label: "文档解析", icon: File, category: "data" },
  { type: "webhook", label: "Webhook", icon: Link, category: "data" },
  { type: "mcp_tool", label: "MCP工具", icon: Puzzle, category: "data" },
  { type: "wait", label: "等待", icon: Clock, category: "data" },
];

const CATEGORY_COLORS: Record<NodeCategory, string> = {
  control: "bg-green-100 text-green-800 border-green-200",
  ai: "bg-purple-100 text-purple-800 border-purple-200",
  data: "bg-blue-100 text-blue-800 border-blue-200",
  integration: "bg-orange-100 text-orange-800 border-orange-200",
};

const CATEGORY_LABELS: Record<NodeCategory, string> = {
  control: "控制流",
  ai: "AI核心",
  data: "数据处理",
  integration: "集成",
};

export function NodePalette() {
  const onDragStart = (event: React.DragEvent, item: PaletteItem) => {
    event.dataTransfer.setData("application/reactflow/type", item.type);
    event.dataTransfer.setData("application/reactflow/label", item.label);
    event.dataTransfer.effectAllowed = "move";
  };

  const categories: NodeCategory[] = ["control", "ai", "data"];

  return (
    <div className="w-64 bg-white border-r border-gray-200 overflow-y-auto">
      <div className="p-4 border-b border-gray-100">
        <h2 className="text-sm font-semibold text-gray-600">节点面板</h2>
      </div>

      {categories.map((cat) => (
        <div key={cat} className="p-3">
          <h3
            className={`text-xs font-medium px-2 py-1 rounded border ${CATEGORY_COLORS[cat]} mb-2`}
          >
            {CATEGORY_LABELS[cat]}
          </h3>
          <div className="grid grid-cols-2 gap-1.5">
            {PALETTE_ITEMS.filter((item) => item.category === cat).map(
              (item) => (
                <div
                  key={item.type}
                  className="flex flex-col items-center gap-1 p-2 rounded-md cursor-grab hover:bg-gray-50 border border-transparent hover:border-gray-200 transition-colors"
                  draggable
                  onDragStart={(e) => onDragStart(e, item)}
                >
                  <item.icon size={18} className="text-gray-600" />
                  <span className="text-[10px] text-gray-500 text-center leading-tight">
                    {item.label}
                  </span>
                </div>
              )
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
