import pathlib

path1 = pathlib.Path('app/domain/services/causal_graph_service.py')
text1 = path1.read_text()
old1 = "    def traverse_dependencies(\n        self, graph: RecoveryGraph, start_node_id: str, direction: str = \"downstream\", limit: int = 100\n    ) -> list[GraphNode]:"
new1 = "    def traverse_dependencies(\n        self,\n        graph: RecoveryGraph,\n        start_node_id: str,\n        direction: str = \"downstream\",\n        limit: int = 100,\n    ) -> list[GraphNode]:"
path1.write_text(text1.replace(old1, new1))

path2 = pathlib.Path('app/domain/services/graph_integration_service.py')
text2 = path2.read_text()
old2 = "                r_edge_id = self._edge_id(rid, graph_node.node_id, GraphRelation.OBSERVED_AT, tenant_id)"
new2 = "                r_edge_id = self._edge_id(\n                    rid,\n                    graph_node.node_id,\n                    GraphRelation.OBSERVED_AT,\n                    tenant_id,\n                )"
path2.write_text(text2.replace(old2, new2))
print('done')
