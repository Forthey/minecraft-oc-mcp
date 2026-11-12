package com.pathfinding;

import java.util.*;


public class MicroPlanner {
    // Штраф за подъем на 1 блок (например, 5.0 значит, что 1 блок вверх = 5 блоков по горизонтали)
    public static final double CLIMB_PENALTY = 5.0;
    // Штраф за спуск (спускаться обычно быстрее, чем подниматься)
    public static final double DESCEND_PENALTY = 1.0;

    public static final int FLIGHT_ALTITUDE = 3;

    private record Node(int x, int z, double f) {}

    /**
     * Ищет путь по склеенной карте высот.
     * @param stitchedMap Карта высот (512x1024 или 1024x512)
     * @param startX Локальный X старта в склеенной карте
     * @param startZ Локальный Z старта в склеенной карте
     * @param goalX Локальный X цели в склеенной карте
     * @param goalZ Локальный Z цели в склеенной карте
     * @param worldOffsetX Смещение для перевода локального X в мировой
     * @param worldOffsetZ Смещение для перевода локального Z в мировой
     * @return Список мировых координат [x, y, z]
     */
    public static List<int[]> findPath(int[][] stitchedMap,
                                       int startX, int startZ, int startY,
                                       int goalX, int goalZ, int goalY,
                                       int worldOffsetX, int worldOffsetZ) {

        int width = stitchedMap.length;
        int height = stitchedMap[0].length;

        PriorityQueue<Node> openSet = new PriorityQueue<>(Comparator.comparingDouble(n -> n.f));
        Map<Long, Double> gScore = new HashMap<>();
        Map<Long, Long> cameFrom = new HashMap<>();

        long startKey = key(startX, startZ);
        gScore.put(startKey, 0.0);
        openSet.add(new Node(startX, startZ, heuristic(startX, startZ, goalX, goalZ)));

        long goalKey = key(goalX, goalZ);
        boolean found = false;

        int[][] dirs = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}}; // Восток, Запад, Юг, Север

        while (!openSet.isEmpty()) {
            Node current = openSet.poll();
            long curKey = key(current.x, current.z);

            if (curKey == goalKey) {
                found = true;
                break;
            }

            double currentG = gScore.get(curKey);
            int hCurrent = stitchedMap[current.x][current.z];

            for (int[] d : dirs) {
                int nx = current.x + d[0];
                int nz = current.z + d[1];

                // Проверка границ
                if (nx < 0 || nx >= width || nz < 0 || nz >= height) continue;

                int hNext = stitchedMap[nx][nz];
                // Бездна (0) или неизвестный блок - непроходимо
                if (hNext <= 0 || hCurrent <= 0) continue;

                // Стоимость шага
                double stepCost = 1.0;
                if (hNext > hCurrent) {
                    stepCost += (hNext - hCurrent) * CLIMB_PENALTY; // Подъем
                } else if (hNext < hCurrent) {
                    stepCost += (hCurrent - hNext) * DESCEND_PENALTY; // Спуск
                }

                double tentativeG = currentG + stepCost;
                long nKey = key(nx, nz);

                if (tentativeG < gScore.getOrDefault(nKey, Double.POSITIVE_INFINITY)) {
                    cameFrom.put(nKey, curKey);
                    gScore.put(nKey, tentativeG);
                    double f = tentativeG + heuristic(nx, nz, goalX, goalZ);
                    openSet.add(new Node(nx, nz, f));
                }
            }
        }

        if (!found) return null; // Путь не найден

        // Восстанавливаем путь (с конца в начало)
        LinkedList<int[]> path = new LinkedList<>();
        long curr = goalKey;

        while (curr != startKey) {
            int x = (int) (curr >> 32);
            int z = (int) (curr & 0xFFFFFFFFL);

            int worldX = worldOffsetX + x;
            int worldZ = worldOffsetZ + z;

            // Вычисляем Y: если это финиш, берем реальную высоту цели. Иначе - высота поверхности + 3.
            int worldY;
            if (x == goalX && z == goalZ) {
                worldY = goalY;
            } else {
                worldY = stitchedMap[x][z] + FLIGHT_ALTITUDE;
            }

            path.addFirst(new int[]{worldX, worldY, worldZ});
            curr = cameFrom.get(curr);
        }

        // Добавляем стартовую точку (реальная высота робота на старте)
        int sx = (int) (startKey >> 32);
        int sz = (int) (startKey & 0xFFFFFFFFL);
        path.addFirst(new int[]{worldOffsetX + sx, startY, worldOffsetZ + sz});

        return expandVerticalMoves(path);
    }

    private static double heuristic(int x1, int z1, int x2, int z2) {
        // Манхэттенское расстояние
        return Math.abs(x1 - x2) + Math.abs(z1 - z2);
    }

    private static long key(int x, int z) {
        return ((long) x << 32) | (z & 0xFFFFFFFFL);
    }

    /**
     * A* выдает только точки поворота. Нам нужно развернуть подъемы/спуски
     * в вертикальные шаги (например, x:10, z:5, y:64 -> x:10, z:5, y:65).
     */
    private static List<int[]> expandVerticalMoves(List<int[]> coarsePath) {
        List<int[]> fullPath = new ArrayList<>();
        if (coarsePath.isEmpty()) return fullPath;

        fullPath.add(coarsePath.get(0));

        for (int i = 1; i < coarsePath.size(); i++) {
            int[] prev = coarsePath.get(i - 1);
            int[] next = coarsePath.get(i);

            int dx = next[0] - prev[0];
            int dz = next[2] - prev[2];
            int dy = next[1] - prev[1];

            // Если это вертикальный подъем/спуск (dx и dz равны 0, а dy != 0)
            // или горизонтальный шаг с изменением высоты
            if (dy > 0) {
                // Сначала летим вверх над текущей колонкой
                for (int y = 1; y <= dy; y++) {
                    fullPath.add(new int[]{prev[0], prev[1] + y, prev[2]});
                }
                // Затем движемся горизонтально
                if (dx != 0 || dz != 0) {
                    fullPath.add(next);
                }
            } else if (dy < 0) {
                // Сначала движемся горизонтально на текущей высоте
                if (dx != 0 || dz != 0) {
                    fullPath.add(new int[]{next[0], prev[1], next[2]});
                }
                // Затем спускаемся вниз
                for (int y = 1; y <= -dy; y++) {
                    fullPath.add(new int[]{next[0], prev[1] - y, next[2]});
                }
            } else {
                // Обычный горизонтальный шаг
                fullPath.add(next);
            }
        }
        return fullPath;
    }
}