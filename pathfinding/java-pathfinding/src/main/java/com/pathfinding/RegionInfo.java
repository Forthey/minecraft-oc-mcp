package com.pathfinding;

public final class RegionInfo {
    public final RegionCoord coord;
    public final boolean exists;
    public final double costFactor;
    public final double voidFraction;
    public final double missingFraction;
    public final int samplesCount;
    public final double avgDelta;

    public RegionInfo(RegionCoord coord, boolean exists, double costFactor,
                      double voidFraction, double missingFraction,
                      int samplesCount, double avgDelta) {
        this.coord = coord;
        this.exists = exists;
        this.costFactor = costFactor;
        this.voidFraction = voidFraction;
        this.missingFraction = missingFraction;
        this.samplesCount = samplesCount;
        this.avgDelta = avgDelta;
    }

    public static RegionInfo nonExistent(RegionCoord c) {
        return new RegionInfo(c, false, 3.0, 0, 0, 0, 0);
    }
    public static RegionInfo impossible(RegionCoord c, double vf, double mf, int s) {
        return new RegionInfo(c, true, Double.POSITIVE_INFINITY, vf, mf, s, 0);
    }
    public static RegionInfo lowData(RegionCoord c, double vf, double mf, int s) {
        return new RegionInfo(c, true, 3.0, vf, mf, s, 0);
    }
}