package com.pathfinding;

import java.util.ArrayList;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        if (args.length < 8) {
            System.err.println("Использование: java -jar pathfinding.jar <путь_к_миру> <X1> <Y1> <Z1> <X2> <Y2> <Z2> <Направление>");
            System.err.println("Направление: North, South, East, West");
            System.exit(1);
        }

        String world = args[0];
        int startX = Integer.parseInt(args[1]);
        int startY = Integer.parseInt(args[2]);
        int startZ = Integer.parseInt(args[3]);

        int goalX = Integer.parseInt(args[4]);
        int goalY = Integer.parseInt(args[5]);
        int goalZ = Integer.parseInt(args[6]);

        String initialFacing = args[7];

        double[] start = {startX, startY, startZ};
        double[] goal  = {goalX, goalY, goalZ};

        RegionCostEstimator estimator = new RegionCostEstimator(world);

        List<RegionCoord> route = new MacroPlanner(estimator).plan(start, goal);
        System.err.println("Маршрут регионов: " + route);

        int[] currentPos = {startX, startY, startZ};
        int[] finalGoal = {goalX, goalY, goalZ};
        List<int[]> allBlockPath = new ArrayList<>();

        if (route.size() == 1) {
            System.err.println("Цель в том же регионе. Строим локальный маршрут.");
            RegionCoord reg = route.get(0);
            int[][] map = estimator.getFullHeightmap(reg);
            if (map == null) {
                System.err.println("Ошибка чтения региона!");
                System.exit(1);
            }

            int offsetX = reg.x() * 512;
            int offsetZ = reg.z() * 512;

            int startLocalX = currentPos[0] - offsetX;
            int startLocalZ = currentPos[2] - offsetZ;
            int goalLocalX = finalGoal[0] - offsetX;
            int goalLocalZ = finalGoal[2] - offsetZ;

            List<int[]> segment = MicroPlanner.findPath(
                    map,
                    startLocalX, startLocalZ, currentPos[1],
                    goalLocalX, goalLocalZ, finalGoal[1],
                    offsetX, offsetZ
            );
            if (segment != null) {
                allBlockPath.addAll(segment);
            } else {
                System.err.println("Микро-путь не найден.");
                System.exit(1);
            }
        } else {
            for (int i = 0; i < route.size() - 1; i++) {
                RegionCoord regA = route.get(i);
                RegionCoord regB = route.get(i + 1);

                boolean alongX = Math.abs(regA.x() - regB.x()) > 0;
                int[][] map = estimator.getStitchedHeightmap(regA, regB, alongX);
                if (map == null) {
                    System.err.println("Ошибка склейки регионов " + regA + " и " + regB);
                    System.exit(1);
                }

                int offsetX = Math.min(regA.x(), regB.x()) * 512;
                int offsetZ = Math.min(regA.z(), regB.z()) * 512;

                int startLocalX = currentPos[0] - offsetX;
                int startLocalZ = currentPos[2] - offsetZ;

                int goalLocalX, goalLocalZ;

                if (i == route.size() - 2) {
                    goalLocalX = finalGoal[0] - offsetX;
                    goalLocalZ = finalGoal[2] - offsetZ;
                } else {
                    RegionCoord regC = route.get(i + 2);
                    double edgeX = regB.x() * 512.0 + 256.0;
                    double edgeZ = regB.z() * 512.0 + 256.0;

                    if (regC.x() > regB.x()) edgeX = regB.x() * 512.0 + 511.0;
                    else if (regC.x() < regB.x()) edgeX = regB.x() * 512.0;
                    else if (regC.z() > regB.z()) edgeZ = regB.z() * 512.0 + 511.0;
                    else if (regC.z() < regB.z()) edgeZ = regB.z() * 512.0;

                    goalLocalX = (int) edgeX - offsetX;
                    goalLocalZ = (int) edgeZ - offsetZ;
                }

                System.err.println("Строим сегмент " + (i + 1) + "/" + (route.size() - 1) + ": " + regA + " -> " + regB);
                List<int[]> segment = MicroPlanner.findPath(
                        map,
                        startLocalX, startLocalZ, currentPos[1],
                        goalLocalX, goalLocalZ, finalGoal[1],
                        offsetX, offsetZ
                );

                if (segment == null) {
                    System.err.println("Микро-путь не найден на отрезке " + regA + " -> " + regB);
                    System.exit(1);
                }

                if (allBlockPath.isEmpty()) {
                    allBlockPath.addAll(segment);
                } else {
                    allBlockPath.addAll(segment.subList(1, segment.size()));
                }

                int[] lastPoint = segment.get(segment.size() - 1);
                currentPos[0] = lastPoint[0];
                currentPos[1] = lastPoint[1];
                currentPos[2] = lastPoint[2];
            }
        }

        // 6. Сжатие пути
        List<String> absoluteCommands = PathCompressor.compress(allBlockPath);

        // 7. Преобразование в относительные команды
        List<String> relativeCommands = RelativePathConverter.convert(absoluteCommands, initialFacing);

        // Выводим в stdout ТОЛЬКО итоговые команды
        for (String cmd : relativeCommands) {
            System.out.println(cmd);
        }
    }
}