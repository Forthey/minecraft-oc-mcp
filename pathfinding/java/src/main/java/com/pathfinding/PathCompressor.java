package com.pathfinding;

import java.util.ArrayList;
import java.util.List;

public class PathCompressor {

    public static List<String> compress(List<int[]> path) {
        List<String> commands = new ArrayList<>();
        if (path == null || path.size() < 2) return commands;

        String currentDir = null;
        int count = 0;

        for (int i = 1; i < path.size(); i++) {
            int[] prev = path.get(i - 1);
            int[] curr = path.get(i);

            int dx = curr[0] - prev[0];
            int dy = curr[1] - prev[1];
            int dz = curr[2] - prev[2];

            String dir = getDirection(dx, dy, dz);

            if (dir == null) continue; // Если нет движения, пропускаем

            if (dir.equals(currentDir)) {
                count++;
            } else {
                if (currentDir != null) {
                    commands.add(currentDir + " " + count);
                }
                currentDir = dir;
                count = 1;
            }
        }

        // Добавляем последнюю команду
        if (currentDir != null) {
            commands.add(currentDir + " " + count);
        }

        return commands;
    }

    private static String getDirection(int dx, int dy, int dz) {
        // Приоритет: Вертикаль, затем Запад/Восток, затем Север/Юг
        if (dy > 0) return "Up";
        if (dy < 0) return "Down";
        if (dx > 0) return "East";  // +X
        if (dx < 0) return "West";  // -X
        if (dz > 0) return "South"; // +Z
        if (dz < 0) return "North"; // -Z
        return null;
    }
}