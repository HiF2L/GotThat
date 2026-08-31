import re
import heapq
import networkx as nx
from typing import List, Dict, Set, Tuple, Optional, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.ontology import Concept, ConceptDependency, DependencyType
from app.models.mastery import UserMasteryState
from app.schemas.tutor import PlannedDAGSchema, DAGNodeSchema, DAGEdgeSchema


def natural_sort_key(code: Optional[str], fallback_index: int = 0) -> tuple:
    """
    Parses code strings like 'M1.02', 'MOD2.05', 'CS.1.3', 'STEP.10' into natural comparison tuples:
    e.g. 'M1.02' -> ('m', 1, 2, fallback_index)
         'STEP.10' -> ('step', 10, fallback_index)
    Ensures natural numerical ordering across module numbers and sub-lesson indices.
    """
    if not code:
        return ("", fallback_index)
    parts = re.split(r'(\d+)', str(code))
    parsed = []
    for p in parts:
        if p.isdigit():
            parsed.append(int(p))
        elif p:
            parsed.append(p.lower().strip(" .-_"))
    parsed.append(fallback_index)
    return tuple(parsed)


def deterministic_topological_sort(
    nodes: List[Any],
    dependencies: List[Tuple[str, str]],
    key_func: Optional[Any] = None,
) -> List[Any]:
    """
    Performs Kahn's algorithm with a priority queue (min-heap) using natural sorting as tie-breaker.
    Guarantees:
    1. Prerequisite Invariant: If (A, B) in dependencies (A is prerequisite of B), A appears before B.
    2. Pedagogical Sequence Invariant: Among all candidate concepts with 0 unsatisfied prerequisites,
       they are chosen in natural pedagogical sequence (module code / definition index).
    3. Determinism: Output is 100% stable regardless of SQL row insertion or dictionary hashing order.
    """
    if not nodes:
        return []

    def get_node_id(n):
        if isinstance(n, dict):
            return n.get("id") or n.get("concept_id") or ""
        elif hasattr(n, "id"):
            return str(n.id)
        return str(n)

    def get_node_code(n):
        if isinstance(n, dict):
            return n.get("code") or n.get("concept_code") or ""
        elif hasattr(n, "code"):
            return str(n.code or "")
        return ""

    node_map = {}
    orig_indices = {}
    for idx, n in enumerate(nodes):
        nid = get_node_id(n)
        node_map[nid] = n
        orig_indices[nid] = idx

    in_degree = {nid: 0 for nid in node_map}
    adj = {nid: [] for nid in node_map}

    for src, tgt in dependencies:
        src_id = str(src)
        tgt_id = str(tgt)
        if src_id in in_degree and tgt_id in in_degree:
            adj[src_id].append(tgt_id)
            in_degree[tgt_id] += 1

    # Initialize priority queue
    # Heap element: (natural_sort_key, orig_index, node_id)
    heap = []
    for nid, deg in in_degree.items():
        if deg == 0:
            n_obj = node_map[nid]
            sort_key = key_func(n_obj, orig_indices[nid]) if key_func else natural_sort_key(get_node_code(n_obj), orig_indices[nid])
            heapq.heappush(heap, (sort_key, orig_indices[nid], nid))

    sorted_result = []
    while heap:
        _, _, curr_id = heapq.heappop(heap)
        sorted_result.append(node_map[curr_id])
        for neighbor_id in adj[curr_id]:
            in_degree[neighbor_id] -= 1
            if in_degree[neighbor_id] == 0:
                neighbor_obj = node_map[neighbor_id]
                sort_key = key_func(neighbor_obj, orig_indices[neighbor_id]) if key_func else natural_sort_key(get_node_code(neighbor_obj), orig_indices[neighbor_id])
                heapq.heappush(heap, (sort_key, orig_indices[neighbor_id], neighbor_id))

    if len(sorted_result) < len(nodes):
        # Fallback if circular dependency or disconnected node: append remaining in original order
        seen_ids = {get_node_id(x) for x in sorted_result}
        for n in nodes:
            if get_node_id(n) not in seen_ids:
                sorted_result.append(n)

    return sorted_result


class KnowledgeGraphService:
    """
    Manages graph traversal, topological sorting, dependency analysis,
    and adaptive pruning of prerequisites based on student mastery.
    """

    async def get_prerequisite_subgraph(
        self,
        session: AsyncSession,
        target_concept_id: str,
    ) -> nx.DiGraph:
        """
        Extracts the full transitive dependency DAG ending at target_concept_id.
        """
        # Fetch all concepts and dependencies
        deps_res = await session.execute(select(ConceptDependency))
        deps = deps_res.scalars().all()

        concepts_res = await session.execute(select(Concept))
        concepts_map = {c.id: c for c in concepts_res.scalars().all()}

        # Build complete networkx DiGraph
        full_graph = nx.DiGraph()
        for c in concepts_map.values():
            full_graph.add_node(c.id, code=c.code, title=c.title, concept=c)

        for d in deps:
            full_graph.add_edge(d.source_concept_id, d.target_concept_id, relation_type=d.relation_type.value)

        # Extract target concept and track context
        if target_concept_id not in full_graph:
            return nx.DiGraph()

        target_concept_res = await session.execute(
            select(Concept).where(Concept.id == target_concept_id)
        )
        target_concept = target_concept_res.scalars().first()

        # If concept belongs to a track, ensure the entire track's connected learning arc is included
        if target_concept and target_concept.track_id:
            track_concepts_res = await session.execute(
                select(Concept).where(Concept.track_id == target_concept.track_id)
            )
            track_concepts = track_concepts_res.scalars().all()
            track_concept_ids = {c.id for c in track_concepts}

            # Find terminal apex node of this track (out-degree 0 in track subgraph)
            track_subgraph = full_graph.subgraph(track_concept_ids)
            terminal_nodes = [n for n in track_subgraph.nodes() if track_subgraph.out_degree(n) == 0]
            apex_goal_id = terminal_nodes[-1] if terminal_nodes else target_concept.id

            ancestors = nx.ancestors(full_graph, apex_goal_id)
            subgraph_nodes = ancestors.union({apex_goal_id}).union(track_concept_ids)
            return full_graph.subgraph(subgraph_nodes).copy()

        ancestors = nx.ancestors(full_graph, target_concept_id)
        subgraph_nodes = ancestors.union({target_concept_id})

        return full_graph.subgraph(subgraph_nodes).copy()

    async def plan_curriculum_dag(
        self,
        session: AsyncSession,
        user_id: str,
        target_concept_id: str,
        mastery_threshold: float = 0.85,
    ) -> PlannedDAGSchema:
        """
        Builds the tailored learning DAG for the student:
        - Retrieves prerequisite subgraph
        - Sorts deterministically using stable topological sort
        - Marks nodes as 'completed', 'active', 'pending'
        - Prunes mastered concepts while preserving connection integrity
        - Generates clean Mermaid graph representation
        """
        subgraph = await self.get_prerequisite_subgraph(session, target_concept_id)

        # Get user mastery states
        mastery_res = await session.execute(
            select(UserMasteryState).where(UserMasteryState.user_id == user_id)
        )
        user_mastery = {m.concept_id: m for m in mastery_res.scalars().all()}

        # Extract nodes and dependencies for deterministic topological sort
        node_ids_list = list(subgraph.nodes())
        node_objs = []
        for nid in node_ids_list:
            nd = subgraph.nodes[nid]
            c_obj = nd.get("concept")
            node_objs.append({
                "id": nid,
                "code": nd.get("code") or (c_obj.code if c_obj else nid),
                "title": nd.get("title") or (c_obj.title if c_obj else "Concept"),
                "slug": nd.get("slug") or (c_obj.slug if c_obj else None),
                "node_data": nd,
            })

        subgraph_deps = [(u, v) for u, v in subgraph.edges()]
        sorted_node_dicts = deterministic_topological_sort(node_objs, subgraph_deps)

        nodes_schema: List[DAGNodeSchema] = []
        first_pending_found = False

        for n_dict in sorted_node_dicts:
            node_id = n_dict["id"]
            node_data = n_dict["node_data"]
            m_state = user_mastery.get(node_id)
            m_prob = m_state.mastery_prob if m_state else 0.0
            unc = m_state.uncertainty if m_state else 1.0
            is_mastered = (m_prob >= mastery_threshold) or (m_prob >= 0.80 and unc <= 0.40)

            if is_mastered:
                status = "completed"
            elif not first_pending_found:
                status = "active"
                first_pending_found = True
            else:
                status = "pending"

            nodes_schema.append(
                DAGNodeSchema(
                    id=node_id,
                    code=n_dict.get("code", node_id),
                    title=n_dict.get("title", "Concept"),
                    slug=n_dict.get("slug"),
                    status=status,
                    mastery_prob=m_prob,
                )
            )

        edges_schema: List[DAGEdgeSchema] = []
        for u, v, data in subgraph.edges(data=True):
            edges_schema.append(
                DAGEdgeSchema(
                    source=u,
                    target=v,
                    relation_type=data.get("relation_type", "strict_prerequisite"),
                )
            )

        # Build Mermaid graph code
        mermaid_lines = ["graph TD"]
        for node in nodes_schema:
            clean_title = node.title.replace('"', "'")
            # Style nodes based on status
            if node.status == "completed":
                mermaid_lines.append(f'    {node.code}["✔ {clean_title}"]:::completed')
            elif node.status == "active":
                mermaid_lines.append(f'    {node.code}["▶ {clean_title}"]:::active')
            else:
                mermaid_lines.append(f'    {node.code}["{clean_title}"]:::pending')

        for u, v, _ in subgraph.edges(data=True):
            u_code = subgraph.nodes[u].get("code", u)
            v_code = subgraph.nodes[v].get("code", v)
            mermaid_lines.append(f"    {u_code} --> {v_code}")

        mermaid_lines.append("    classDef completed fill:#10B981,stroke:#059669,stroke-width:2px,color:#fff;")
        mermaid_lines.append("    classDef active fill:#6366F1,stroke:#4F46E5,stroke-width:3px,color:#fff;")
        mermaid_lines.append("    classDef pending fill:#1E293B,stroke:#475569,stroke-width:1px,color:#94A3B8;")

        mermaid_code = "\n".join(mermaid_lines)
        completed_count = sum(1 for n in nodes_schema if n.status == "completed")

        return PlannedDAGSchema(
            mermaid_code=mermaid_code,
            nodes=nodes_schema,
            edges=edges_schema,
            total_nodes=len(nodes_schema),
            completed_nodes=completed_count,
        )


knowledge_graph_service = KnowledgeGraphService()
