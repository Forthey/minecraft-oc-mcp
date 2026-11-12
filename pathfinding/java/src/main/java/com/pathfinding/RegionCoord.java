package com.pathfinding;

public record RegionCoord(int x, int z) {
    public static RegionCoord fromWorld(double wx, double wz) {
        return new RegionCoord(
                (int) Math.floor(wx / 512.0),
                (int) Math.floor(wz / 512.0)
        );
    }

    public int[] bounds() {
        int x0 = x * 512, z0 = z * 512;
        return new int[]{x0, x0 + 511, z0, z0 + 511};
    }
}