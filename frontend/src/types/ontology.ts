/**
 * Subgraph payload from `GET /api/ontology/graph`. Shape matches
 * `react-force-graph-2d` expectations.
 */

export interface GraphNode {
  id: string;
  ticker: string;
  name: string;
  market: string;
  sector: string | null;
  tier: number;
  is_center: boolean;
  today_change_pct: number | null;
  node_kind?: "stock" | "private" | "theme" | "macro";
  is_virtual?: boolean;
}

export interface GraphLink {
  source: string;
  target: string;
  relation_type: string;
  signal_direction: "positive" | "negative" | "inverse";
  strength: number;
  confidence: number;
  src_label: string;
  src_url: string | null;
  rationale: string | null;
  target_in_universe: boolean;
}

export interface GraphPayload {
  center: string;
  nodes: GraphNode[];
  links: GraphLink[];
}
