package com.pathfinding;

import java.util.*;

public class MacroPlanner {
    private static final double MIN_COST_FACTOR = 0.5;
    private static final double MAX_COST_FACTOR = 50.0;

    private final RegionCostEstimator estimator;
    private final int margin;

    public MacroPlanner(RegionCostEstimator estimator) { this(estimator, 2); }
    public MacroPlanner(RegionCostEstimator estimator, int margin) {
        this.estimator = estimator;
        this.margin = margin;
    }

    public List<RegionCoord> plan(double[] start, double[] goal) {
        RegionCoord s = RegionCoord.fromWorld(start[0], start[2]);
        RegionCoord g = RegionCoord.fromWorld(goal[0], goal[2]);
        if (s.equals(g)) return List.of(s);

        int minX = Math.min(s.x(), g.x()) - margin;
        int maxX = Math.max(s.x(), g.x()) + margin;
        int minZ = Math.min(s.z(), g.z()) - margin;
        int maxZ = Math.max(s.z(), g.z()) + margin;

        // Параллельный прогрев — все регионы в коридоре оцениваются одновременно
        List<RegionCoord> all = new ArrayList<>();
        for (int x = minX; x <= maxX; x++)
            for (int z = minZ; z <= maxZ; z++)
                all.add(new RegionCoord(x, z));
        estimator.prewarm(all);

        return astar(s, g, minX, maxX, minZ, maxZ);
    }

    private List<RegionCoord> astar(RegionCoord start, RegionCoord goal,
                                    int minX, int maxX, int minZ, int maxZ) {
        record Node(RegionCoord c, double f) {}
        PriorityQueue<Node> open = new PriorityQueue<>(Comparator.comparingDouble(n -> n.f));
        Map<RegionCoord, Double> gScore = new HashMap<>();
        Map<RegionCoord, RegionCoord> cameFrom = new HashMap<>();
        Set<RegionCoord> closed = new HashSet<>();

        gScore.put(start, 0.0);
        open.add(new Node(start, heuristic(start, goal)));

        while (!open.isEmpty()) {
            RegionCoord cur = open.poll().c;
            if (closed.contains(cur)) continue;
            if (cur.equals(goal)) return reconstruct(cameFrom, cur);
            closed.add(cur);

            for (RegionCoord n : neighbors(cur, minX, maxX, minZ, maxZ)) {
                if (closed.contains(n)) continue;
                double w = edgeWeight(estimator.estimate(n));
                double tentative = gScore.get(cur) + w;
                if (tentative < gScore.getOrDefault(n, Double.POSITIVE_INFINITY)) {
                    gScore.put(n, tentative);
                    cameFrom.put(n, cur);
                    double f = tentative + heuristic(n, goal);
                    open.add(new Node(n, f));
                }
            }
        }
        throw new RuntimeException("No path found between regions");
    }

    private static double heuristic(RegionCoord a, RegionCoord b) {
        int manhattan = Math.abs(a.x() - b.x()) + Math.abs(a.z() - b.z());
        return manhattan * 512.0 * MIN_COST_FACTOR;
    }

    private static double edgeWeight(RegionInfo info) {
        double c = info.costFactor;
        if (Double.isInfinite(c)) return 512.0 * MAX_COST_FACTOR;
        return 512.0 * c;
    }

    private static Iterable<RegionCoord> neighbors(RegionCoord c,
                                                   int minX, int maxX, int minZ, int maxZ) {
        List<RegionCoord> out = new ArrayList<>(4);
        int[][] dirs = {{1,0},{-1,0},{0,1},{0,-1}};
        for (int[] d : dirs) {
            int nx = c.x() + d[0], nz = c.z() + d[1];
            if (nx >= minX && nx <= maxX && nz >= minZ && nz <= maxZ)
                out.add(new RegionCoord(nx, nz));
        }
        return out;
    }

    private static List<RegionCoord> reconstruct(Map<RegionCoord, RegionCoord> cameFrom,
                                                 RegionCoord cur) {
        LinkedList<RegionCoord> path = new LinkedList<>();
        path.add(cur);
        while (cameFrom.containsKey(cur)) {
            cur = cameFrom.get(cur);
            path.addFirst(cur);
        }
        return path;
    }
}