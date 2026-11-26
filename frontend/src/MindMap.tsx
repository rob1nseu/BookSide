import { memo, useMemo, useState, useEffect } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  useReactFlow,
  type NodeProps,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Prose } from "./components";
export type Concept = {
  id: string;
  parent_id: string | null;
  label: string;
  summary: string;
  chapter_id: string;
  sources: string[];
};
type ConceptNode = Node<
  {
    label: string;
    state: string;
    selected: boolean;
    hasChildren: boolean;
    collapsed: boolean;
    toggle: () => void;
  },
  "concept"
>;
const ConceptCard = memo(function ConceptCard({
  data,
}: NodeProps<ConceptNode>) {
  return (
    <div className={"concept-node " + (data.selected ? "selected" : "")}>
      <Handle type="target" position={Position.Left} />
      <strong>
        <Prose inline>{data.label}</Prose>
      </strong>
      <small>{data.state}</small>
      {data.hasChildren && (
        <button
          className="nodrag"
          aria-label={(data.collapsed ? "展开" : "折叠") + data.label}
          onClick={(e) => {
            e.stopPropagation();
            data.toggle();
          }}
        >
          {data.collapsed ? "＋" : "−"}
        </button>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
});
const nodeTypes = { concept: ConceptCard };
function Fit({ signature }: { signature: string }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const id = requestAnimationFrame(
      () => void fitView({ padding: 0.18, maxZoom: 1 }),
    );
    return () => cancelAnimationFrame(id);
  }, [signature, fitView]);
  return null;
}
export default function MindMap({
  title,
  concepts,
  states,
  selected,
  onSelect,
}: {
  title: string;
  concepts: Concept[];
  states: Record<string, string>;
  selected: string;
  onSelect: (id: string) => void;
}) {
  const [collapsed, setCollapsed] = useState<Set<string>>(
    () => new Set(concepts.filter((n) => n.parent_id).map((n) => n.id)),
  );
  const [outline, setOutline] = useState(
    () => window.matchMedia("(max-width: 760px)").matches,
  );
  const graph = useMemo(() => {
    const all = [
      { id: "__root", parent_id: null, label: title },
      ...concepts.map((n) => ({ ...n, parent_id: n.parent_id || "__root" })),
    ];
    const nodes: ConceptNode[] = [],
      edges: { id: string; source: string; target: string }[] = [];
    let row = 0;
    function place(id: string, depth: number): number {
      const n = all.find((c) => c.id === id)!;
      const children = all.filter((c) => c.parent_id === id);
      const visible = collapsed.has(id) ? [] : children;
      const ys = visible.map((c) => place(c.id, depth + 1));
      const y = ys.length ? (ys[0] + ys.at(-1)!) / 2 : row++ * 112;
      nodes.push({
        id,
        type: "concept",
        position: { x: depth * 260, y },
        data: {
          label: n.label,
          state: id === "__root" ? "章节总览" : states[id] || "未验证",
          selected: selected === id,
          hasChildren: !!children.length,
          collapsed: collapsed.has(id),
          toggle: () =>
            setCollapsed((old) => {
              const next = new Set(old);
              if (next.has(id)) next.delete(id);
              else next.add(id);
              return next;
            }),
        },
      });
      if (n.parent_id)
        edges.push({ id: "edge-" + id, source: n.parent_id, target: id });
      return y;
    }
    place("__root", 0);
    return { nodes, edges };
  }, [concepts, title, states, selected, collapsed]);
  function tree(parent: string | null): React.ReactNode {
    return concepts
      .filter((c) => c.parent_id === parent)
      .map((c) => (
        <li key={c.id}>
          <button
            aria-pressed={selected === c.id}
            onClick={() => onSelect(c.id)}
          >
            <Prose inline>{c.label}</Prose>
            <small>{states[c.id] || "未验证"}</small>
          </button>
          {concepts.some((n) => n.parent_id === c.id) && (
            <details>
              <summary>展开知识点</summary>
              <ul>{tree(c.id)}</ul>
            </details>
          )}
        </li>
      ));
  }
  return (
    <section className="mindmap">
      <div className="map-toolbar">
        <span>点击知识点查看要点或练习</span>
        <button onClick={() => setOutline(!outline)}>
          {outline ? "图形视图" : "层级列表"}
        </button>
      </div>
      {!outline && (
        <div className="map-canvas">
          <ReactFlow
            nodes={graph.nodes}
            edges={graph.edges}
            nodeTypes={nodeTypes}
            nodesDraggable={false}
            nodesConnectable={false}
            deleteKeyCode={null}
            minZoom={0.2}
            maxZoom={1.8}
            fitView
            onNodeClick={(_, n) => {
              if (n.id !== "__root") onSelect(n.id);
            }}
          >
            <Background />
            <Controls showInteractive={false} />
            <Fit signature={graph.nodes.map((n) => n.id).join(",")} />
          </ReactFlow>
        </div>
      )}
      <ul className={"map-outline " + (outline ? "shown" : "")}>
        {tree(null)}
      </ul>
    </section>
  );
}
