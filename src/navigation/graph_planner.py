"""Dijkstra 기반 경로 탐색과 간선 차단.
실행: python src/navigation/graph_planner.py"""
import heapq
import json
import math
from pathlib import Path


class RouteGraph:
    def __init__(self, map_file):
        data = json.loads(Path(map_file).read_text(encoding="utf-8"))
        self.nodes = {n: tuple(xy) for n, xy in data["nodes"].items()}
        self.adj = {n: [] for n in self.nodes}
        self.blocked_edges = set()
        for u, v in data["edges"]:
            w = math.dist(self.nodes[u], self.nodes[v])
            self.adj[u].append((v, w))
            self.adj[v].append((u, w))

    @staticmethod
    def edge_key(u, v):
        return frozenset((u, v))

    def block_edge(self, u, v):
        if u not in self.nodes or v not in self.nodes or not any(n == v for n, _ in self.adj[u]):
            raise ValueError("Unknown graph edge")
        self.blocked_edges.add(self.edge_key(u, v))

    def plan(self, start, goal):
        if start not in self.nodes or goal not in self.nodes:
            raise ValueError("Unknown node")
        dist, prev, heap = {start: 0.0}, {}, [(0.0, start)]
        while heap:
            cost, u = heapq.heappop(heap)
            if cost > dist[u]:
                continue
            if u == goal:
                break
            for v, weight in self.adj[u]:
                if self.edge_key(u, v) in self.blocked_edges:
                    continue
                new = cost + weight
                if new < dist.get(v, math.inf):
                    dist[v], prev[v] = new, u
                    heapq.heappush(heap, (new, v))
        if goal not in dist:
            return None
        route = [goal]
        while route[-1] != start:
            route.append(prev[route[-1]])
        return route[::-1]

    def plan_via(self, stops):
        route = []
        for start, end in zip(stops, stops[1:]):
            segment = self.plan(start, end)
            if segment is None:
                return None
            route.extend(segment if not route else segment[1:])
        return route


if __name__ == "__main__":
    g = RouteGraph(Path(__file__).with_name("example_map.json"))
    first = g.plan("START", "GOAL")
    print("Unblocked route:", first)
    assert first and first[0] == "START" and first[-1] == "GOAL"
    g.block_edge("B", "GOAL")
    blocked = g.plan("START", "GOAL")
    print("After edge blocking:", blocked)
    assert blocked and all({a, b} != {"B", "GOAL"} for a, b in zip(blocked, blocked[1:]))
