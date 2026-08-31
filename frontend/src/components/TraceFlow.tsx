/**
 * @repo: https://github.com/xiaotuolu/DevSupport-AI
 */
import { ReactFlow, Background, Controls, MarkerType } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

// 节点边框按节点状态着色：绿=成功 红=错误 灰=跳过
const STATUS_COLOR: Record<string, string> = { ok: "#52c41a", error: "#ff4d4f", skip: "#d9d9d9" };

export default function TraceFlow({ steps }: { steps: any[] }) {
  // 每个编排节点一个 React Flow 节点，按顺序横向铺开、奇偶错位避免重叠
  const nodes = steps.map((s, i) => ({
    id: String(i),
    position: { x: i * 220, y: (i % 2) * 90 },
    data: {
      label: (
        <div style={{ textAlign: "left", fontSize: 12 }}>
          <b>{s.agent_name}</b>
          <div>{s.duration_ms}ms · {s.token_usage}tok</div>
          {s.hit_docs?.length > 0 && <div style={{ color: "#888" }}>命中{s.hit_docs.length}篇</div>}
          {s.status === "error" && <div style={{ color: "#ff4d4f" }}>错误</div>}
        </div>
      ),
    },
    style: {
      border: `2px solid ${STATUS_COLOR[s.status] || "#1677ff"}`,
      borderRadius: 8,
      padding: 6,
      width: 180,
      background: "#fff",
    },
  }));
  // 相邻节点串联成有向边，还原 Agent 执行先后顺序
  const edges = steps.slice(1).map((_, i) => ({
    id: `e${i}`,
    source: String(i),
    target: String(i + 1),
    animated: true,
    markerEnd: { type: MarkerType.ArrowClosed },
  }));
  return (
    <div style={{ height: 320, border: "1px solid #eee", borderRadius: 8 }}>
      <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: true }}>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
