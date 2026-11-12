package com.pathfinding;

import java.util.ArrayList;
import java.util.List;

public class RelativePathConverter {

    /**
     * Преобразует абсолютные команды в относительные.
     * @param absoluteCommands Список команд вида "East 10", "Up 3", "North 5".
     * @param initialFacing Начальное направление робота: "North", "South", "East", "West".
     * @return Список команд: "Forward 10", "TurnRight", "Up 3", "TurnLeft", "Forward 5".
     */
    public static List<String> convert(List<String> absoluteCommands, String initialFacing) {
        List<String> relativeCommands = new ArrayList<>();
        String currentFacing = initialFacing;

        // Порядок по часовой стрелке: Север -> Восток -> Юг -> Запад
        String[] cycle = {"North", "East", "South", "West"};

        for (String cmd : absoluteCommands) {
            String[] parts = cmd.split(" ");
            String dir = parts[0];
            int count = Integer.parseInt(parts[1]);

            if (dir.equals("Up") || dir.equals("Down")) {
                // Вертикальные перемещения не меняют направление взгляда
                relativeCommands.add(dir + " " + count);
            } else {
                // Вычисляем, насколько нужно повернуть
                int curIdx = indexOf(cycle, currentFacing);
                int tgtIdx = indexOf(cycle, dir);
                int diff = (tgtIdx - curIdx + 4) % 4;

                if (diff == 1) {
                    relativeCommands.add("TurnRight");
                } else if (diff == 2) {
                    relativeCommands.add("TurnRight");
                    relativeCommands.add("TurnRight");
                } else if (diff == 3) {
                    relativeCommands.add("TurnLeft");
                }

                currentFacing = dir;
                relativeCommands.add("Forward " + count);
            }
        }
        return relativeCommands;
    }

    private static int indexOf(String[] arr, String val) {
        for (int i = 0; i < arr.length; i++) {
            if (arr[i].equals(val)) return i;
        }
        return 0; // По умолчанию Север
    }
}