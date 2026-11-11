package com.pathfinding;

import java.util.List;

public class Main {
    public static void main(String[] args) {
        String world = "/home/ivan/.minecraft/saves/Новый мир-";

        RegionCostEstimator estimator = new RegionCostEstimator(world);

        double[] start = {-71, 102, 152};
        double[] goal  = {-2020, 64, 1782};

        estimator.debug(RegionCoord.fromWorld(start[0], start[2]));
        estimator.debug(RegionCoord.fromWorld(goal[0], goal[2]));

        long t0 = System.nanoTime();
        List<RegionCoord> route = new MacroPlanner(estimator).plan(start, goal);
        long elapsed = (System.nanoTime() - t0) / 1_000_000;

        System.out.printf("%nМаршрут: %d регионов, время: %d ms%n", route.size(), elapsed);
        for (RegionCoord r : route) {
            RegionInfo info = estimator.estimate(r);
            System.out.printf("(%3d,%3d) exists=%s cost=%6.2f void=%.1f%% miss=%.1f%% samples=%d%n",
                    r.x(), r.z(), info.exists, info.costFactor,
                    info.voidFraction * 100, info.missingFraction * 100, info.samplesCount);
        }
    }
}