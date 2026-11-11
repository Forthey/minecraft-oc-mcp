package com.pathfinding;

import java.util.ArrayList;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        String world = "/home/ivan/.minecraft/saves/Новый мир--";
        RegionCostEstimator estimator = new RegionCostEstimator(world);

        double[] start = {-153, 4, -196};
        double[] goal  = {-153, 4, -194};

        // 1. Макро-планирование
        List<RegionCoord> route = new MacroPlanner(estimator).plan(start, goal);
        System.out.println("Маршрут регионов: " + route);

        int[] currentPos = {(int) start[0], (int) start[1], (int) start[2]};
        int[] finalGoal = {(int) goal[0], (int) goal[1], (int) goal[2]};
        List<int[]> allBlockPath = new ArrayList<>();

        // Обрабатываем случай, когда старт и финиш в одном регионе
        if (route.size() == 1) {
            System.out.println("Цель в том же регионе. Строим локальный маршрут.");
            RegionCoord reg = route.get(0);
            int[][] map = estimator.getFullHeightmap(reg);
            if (map == null) {
                System.out.println("Ошибка чтения региона!");
                return;
            }

            int offsetX = reg.x() * 512;
            int offsetZ = reg.z() * 512;

            int startLocalX = currentPos[0] - offsetX;
            int startLocalZ = currentPos[2] - offsetZ;
            int goalLocalX = finalGoal[0] - offsetX;
            int goalLocalZ = finalGoal[2] - offsetZ;

            List<int[]> segment = MicroPlanner.findPath(map, startLocalX, startLocalZ, goalLocalX, goalLocalZ, offsetX, offsetZ);
            if (segment != null) {
                allBlockPath.addAll(segment);
            } else {
                System.out.println("Микро-путь не найден.");
                return;
            }
        } else {
            // Обрабатываем маршрут из нескольких регионов
            for (int i = 0; i < route.size() - 1; i++) {
                RegionCoord regA = route.get(i);
                RegionCoord regB = route.get(i + 1);

                boolean alongX = Math.abs(regA.x() - regB.x()) > 0;
                int[][] map = estimator.getStitchedHeightmap(regA, regB, alongX);
                if (map == null) {
                    System.out.println("Ошибка склейки регионов " + regA + " и " + regB);
                    return;
                }

                int offsetX = Math.min(regA.x(), regB.x()) * 512;
                int offsetZ = Math.min(regA.z(), regB.z()) * 512;

                int startLocalX = currentPos[0] - offsetX;
                int startLocalZ = currentPos[2] - offsetZ;

                int goalLocalX, goalLocalZ;

                // Если это последний отрезок пути (регион B — целевой)
                if (i == route.size() - 2) {
                    goalLocalX = finalGoal[0] - offsetX;
                    goalLocalZ = finalGoal[2] - offsetZ;
                } else {
                    // Если впереди есть еще регионы, идем к краю региона B, граничащему с C
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

                System.out.println("Строим сегмент " + (i + 1) + "/" + (route.size() - 1) + ": " + regA + " -> " + regB);
                List<int[]> segment = MicroPlanner.findPath(map, startLocalX, startLocalZ, goalLocalX, goalLocalZ, offsetX, offsetZ);

                if (segment == null) {
                    System.out.println("Микро-путь не найден на отрезке " + regA + " -> " + regB);
                    return;
                }

                // Добавляем к общему пути. Пропускаем первую точку (кроме самого первого сегмента),
                // так как она дублирует последнюю точку предыдущего сегмента.
                if (allBlockPath.isEmpty()) {
                    allBlockPath.addAll(segment);
                } else {
                    allBlockPath.addAll(segment.subList(1, segment.size()));
                }

                // Обновляем текущую позицию робота в мире (берем последнюю точку сегмента)
                int[] lastPoint = segment.get(segment.size() - 1);
                currentPos[0] = lastPoint[0];
                currentPos[1] = lastPoint[1];
                currentPos[2] = lastPoint[2];
            }
        }

        // 6. Сжатие пути (Абсолютные направления)
        List<String> absoluteCommands = PathCompressor.compress(allBlockPath);

        // 7. Преобразование в относительные команды
        String initialFacing = "North"; // Робот смотрит на Север
        List<String> relativeCommands = RelativePathConverter.convert(absoluteCommands, initialFacing);

        System.out.println("\nАбсолютные команды:");
        for (String cmd : absoluteCommands) {
            System.out.println(cmd);
        }

        System.out.println("\nОтносительные команды для робота:");
        for (String cmd : relativeCommands) {
            System.out.println(cmd);
        }
    }
}