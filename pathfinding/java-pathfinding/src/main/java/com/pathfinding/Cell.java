package com.pathfinding;

/** Ячейка 32×32 сетки региона. */
public final class Cell {
    public enum Kind { SOLID, VOID, MISSING }

    public static final int DEFAULT_HEIGHT = 64;

    public final Kind kind;
    public final int y;
    public final String biome;

    private Cell(Kind kind, int y, String biome) {
        this.kind = kind;
        this.y = y;
        this.biome = biome;
    }

    public static Cell solid(int y, String biome) { return new Cell(Kind.SOLID, y, biome); }
    public static Cell voidCell() { return new Cell(Kind.VOID, 0, null); }
    public static Cell missing()  { return new Cell(Kind.MISSING, 0, null); }

    /** Высота для 2D A*: SOLID → y, MISSING → DEFAULT_HEIGHT, VOID → null. */
    public Integer height() {
        return switch (kind) {
            case SOLID   -> y;
            case MISSING -> DEFAULT_HEIGHT;
            case VOID    -> null;
        };
    }
}