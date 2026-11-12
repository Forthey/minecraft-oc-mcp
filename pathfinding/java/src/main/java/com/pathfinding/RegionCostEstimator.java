package com.pathfinding;

import de.pauleff.jnbt.api.ICompoundTag;
import de.pauleff.jnbt.core.Tag_Compound;
import de.pauleff.jnbt.core.Tag_Byte_Array;
import de.pauleff.jnbt.core.Tag;
import de.pauleff.jnbt.formats.binary.NBTReader;

import java.io.DataInputStream;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.zip.GZIPInputStream;
import java.util.zip.InflaterInputStream;

public class RegionCostEstimator {
    private static final Map<String, Double> BIOME_COST = Map.ofEntries(
            Map.entry("ocean", 0.8), Map.entry("deep_ocean", 0.8),
            Map.entry("warm_ocean", 0.8), Map.entry("plains", 1.0),
            Map.entry("desert", 1.0), Map.entry("forest", 1.1),
            Map.entry("birch_forest", 1.1), Map.entry("taiga", 1.1),
            Map.entry("jungle", 1.2), Map.entry("swamp", 1.2),
            Map.entry("mountains", 1.3), Map.entry("windswept_hills", 1.3),
            Map.entry("snowy_peaks", 1.5), Map.entry("jagged_peaks", 1.5),
            Map.entry("frozen_peaks", 1.5)
    );
    private static final double DEFAULT_BIOME_COST = 1.0;
    private final Path regionDir;
    private final double voidPenalty;
    private final double lowDataThreshold;
    private final Map<RegionCoord, RegionInfo> infoCache = new ConcurrentHashMap<>();
    private final Map<RegionCoord, int[][]> heightmapCache = new ConcurrentHashMap<>();

    public RegionCostEstimator(String worldPath) {
        this(worldPath, 5.0, 0.2);
    }

    public RegionCostEstimator(String worldPath, double voidPenalty, double lowDataThreshold) {
        this.regionDir = Path.of(worldPath).toAbsolutePath().normalize().resolve("region");
        this.voidPenalty = voidPenalty;
        this.lowDataThreshold = lowDataThreshold;
    }

    public RegionInfo estimate(RegionCoord coord) {
        return infoCache.computeIfAbsent(coord, this::computeEstimate);
    }

    public void prewarm(Collection<RegionCoord> coords) {
        coords.parallelStream().forEach(this::estimate);
    }

    /**
     * Возвращает полную карту высот региона 512x512.
     * Значение 0 означает пустоту (void) или отсутствующий чанк.
     */
    public int[][] getFullHeightmap(RegionCoord coord) {
        return heightmapCache.computeIfAbsent(coord, c -> {
            Path path = regionDir.resolve("r." + c.x() + "." + c.z() + ".mca");
            if (!Files.exists(path)) return null;

            int[][] map = new int[512][512];
            try (RandomAccessFile raf = new RandomAccessFile(path.toFile(), "r")) {
                for (int cx = 0; cx < 32; cx++) {
                    for (int cz = 0; cz < 32; cz++) {
                        Tag_Compound chunkNbt = readChunkNBT(raf, cx, cz);
                        if (chunkNbt == null) continue; // Чанк пуст

                        ICompoundTag level = chunkNbt.getCompound("Level");
                        if (level == null) continue;

                        int[] heightMap = level.getIntArray("HeightMap");
                        if (heightMap == null || heightMap.length < 256) continue;

                        // Переносим высоты из чанка (16x16) в общую карту региона
                        for (int bx = 0; bx < 16; bx++) {
                            for (int bz = 0; bz < 16; bz++) {
                                int index = bz * 16 + bx; // порядок ZX в чанке
                                int worldX = cx * 16 + bx;
                                int worldZ = cz * 16 + bz;
                                map[worldX][worldZ] = heightMap[index];
                            }
                        }
                    }
                }
            } catch (Exception e) {
                System.err.println("[Estimator] Ошибка чтения региональной карты " + c + ": " + e.getMessage());
                return null;
            }
            return map;
        });
    }

    public void debug(RegionCoord coord) {
        Path path = regionDir.resolve("r." + coord.x() + "." + coord.z() + ".mca");
        System.out.println("region_dir = " + regionDir);
        System.out.println("путь       = " + path);
        System.out.println("exists     = " + Files.exists(path));

        if (!Files.exists(path)) return;

        try (RandomAccessFile raf = new RandomAccessFile(path.toFile(), "r")) {
            Tag_Compound nbt = readChunkNBT(raf, 8, 8);
            if (nbt != null) {
                ICompoundTag level = nbt.getCompound("Level");
                if (level != null) {
                    System.out.println("Теги внутри Level:");
                    // Перебираем все теги в Level
                    for (Tag<?> tag : ((Tag_Compound) level).getData()) {
                        System.out.printf("  %-15s : %s%n", tag.getName(), tag.getClass().getSimpleName());
                    }

                    // Отдельно проверяем HeightMap
                    if (level.hasTag("HeightMap")) {
                        int[] data = level.getIntArray("HeightMap");
                        System.out.println("\nHeightMap найден! Длина: " + (data == null ? "null" : data.length));
                        if (data != null && data.length > 0) {
                            StringBuilder sb = new StringBuilder("Первые высоты: ");
                            for (int i = 0; i < Math.min(10, data.length); i++) {
                                sb.append(data[i]).append(" ");
                            }
                            System.out.println(sb.toString());
                        }
                    } else {
                        System.out.println("\nHeightMap ОТСУТСТВУЕТ в Level!");
                    }
                } else {
                    System.out.println("Level не найден или это не CompoundTag");
                }
            } else {
                System.out.println("Чанк 8,8 пуст");
            }
        } catch (Exception e) {
            System.out.println("парсинг    = FAIL: " + e.getClass().getSimpleName()
                    + ": " + e.getMessage());
        }
    }

    /**
     * Склеивает два региона в одну карту.
     * @param a Первый регион (текущий).
     * @param b Второй регион (следующий).
     * @param alongX true, если двигаемся по X (Восток/Запад), false - по Z (Север/Юг).
     * @return int[512][1024] если alongX, или int[1024][512] если !alongX.
     */
    public int[][] getStitchedHeightmap(RegionCoord a, RegionCoord b, boolean alongX) {
        int[][] mapA = getFullHeightmap(a);
        int[][] mapB = getFullHeightmap(b);
        if (mapA == null || mapB == null) return null;

        if (alongX) {
            // Двигаемся по X (Восток/Запад). X расширяется до 1024, Z остается 512.
            int[][] stitched = new int[1024][512]; // [X][Z]
            boolean bIsEast = b.x() > a.x();
            for (int x = 0; x < 512; x++) {
                for (int z = 0; z < 512; z++) {
                    if (bIsEast) {
                        stitched[x][z] = mapA[x][z];
                        stitched[x + 512][z] = mapB[x][z];
                    } else {
                        stitched[x][z] = mapB[x][z];
                        stitched[x + 512][z] = mapA[x][z];
                    }
                }
            }
            return stitched;
        } else {
            // Двигаемся по Z (Север/Юг). X остается 512, Z расширяется до 1024.
            int[][] stitched = new int[512][1024]; // [X][Z]
            boolean bIsSouth = b.z() > a.z();
            for (int x = 0; x < 512; x++) {
                for (int z = 0; z < 512; z++) {
                    if (bIsSouth) {
                        stitched[x][z] = mapA[x][z];
                        stitched[x][z + 512] = mapB[x][z];
                    } else {
                        stitched[x][z] = mapB[x][z];
                        stitched[x][z + 512] = mapA[x][z];
                    }
                }
            }
            return stitched;
        }
    }

    private RegionInfo computeEstimate(RegionCoord coord) {
        int[][] fullMap = getFullHeightmap(coord);
        if (fullMap == null) return RegionInfo.nonExistent(coord);

        Cell[][] grid = new Cell[32][32];
        for (int ci = 0; ci < 32; ci++) {
            for (int cj = 0; cj < 32; cj++) {
                // Берем высоту в центре чанка (смещение 8,8)
                int h = fullMap[ci * 16 + 8][cj * 16 + 8];
                if (h <= 0) {
                    grid[ci][cj] = Cell.voidCell();
                } else {
                    grid[ci][cj] = Cell.solid(h, null);
                }
            }
        }
        return computeInfo(coord, grid);
    }

    private Cell[][] sampleGrid(Path path, RegionCoord coord) {
        Cell[][] grid = new Cell[32][32];
        try (RandomAccessFile raf = new RandomAccessFile(path.toFile(), "r")) {
            for (int ci = 0; ci < 32; ci++) {
                for (int cj = 0; cj < 32; cj++) {
                    try {
                        Tag_Compound chunkNbt = readChunkNBT(raf, ci, cj);
                        if (chunkNbt == null) {
                            grid[ci][cj] = Cell.missing();
                        } else {
                            grid[ci][cj] = readCellFromHeightmap(chunkNbt, 8, 8);
                        }
                    } catch (Exception e) {
                        grid[ci][cj] = Cell.missing();
                    }
                }
            }
        } catch (Exception e) {
            System.err.println("[Estimator] Ошибка чтения " + path + ": " + e.getMessage());
            for (int i = 0; i < 32; i++) Arrays.fill(grid[i], Cell.missing());
        }
        return grid;
    }

    /**
     * Читает сырой NBT-тег чанка прямо из файла .mca (формат Anvil).
     * Обходит проверки DataVersion, которые ломают jMCX на 1.7.10.
     */
    private Tag_Compound readChunkNBT(RandomAccessFile raf, int cx, int cz) throws Exception {
        int index = (cx & 31) + (cz & 31) * 32;

        raf.seek(index * 4L);
        int offset = raf.readInt();
        int sectorOffset = offset >>> 8;

        if (sectorOffset == 0) return null;

        raf.seek(sectorOffset * 4096L);
        int length = raf.readInt();
        if (length <= 1) return null;

        byte compressionType = raf.readByte();
        byte[] compressed = new byte[length - 1];
        raf.readFully(compressed);

        InputStream in;
        if (compressionType == 1) {
            in = new GZIPInputStream(new ByteArrayInputStream(compressed));
        } else if (compressionType == 2) {
            in = new InflaterInputStream(new ByteArrayInputStream(compressed));
        } else {
            return null;
        }

        // ИСПРАВЛЕНИЕ: Полностью распаковываем чанк в память
        byte[] decompressed = in.readAllBytes();

        // Теперь jNBT гарантированно прочитает весь массив HeightMap целиком
        try (ByteArrayInputStream bais = new ByteArrayInputStream(decompressed);
             DataInputStream dis = new DataInputStream(bais);
             NBTReader reader = new NBTReader(dis)) {

            return (Tag_Compound) reader.read();
        }
    }


    private Cell readCellFromHeightmap(Tag_Compound chunkNbt, int bx, int bz) {
        ICompoundTag level = chunkNbt.getCompound("Level");
        if (level == null) return Cell.missing();

        // ИСПРАВЛЕНИЕ: Читаем как IntArray
        int[] heightMap = level.getIntArray("HeightMap");

        if (heightMap == null || heightMap.length < 256) {
            return Cell.voidCell();
        }

        int index = bz * 16 + bx; // порядок ZX
        int surfaceY = heightMap[index]; // Уже int, маскировать не нужно

        if (surfaceY <= 0) {
            return Cell.voidCell();
        }
        return Cell.solid(surfaceY, null);
    }

    private RegionInfo computeInfo(RegionCoord coord, Cell[][] grid) {
        int missing = 0, voids = 0;
        for (Cell[] row : grid)
            for (Cell c : row) {
                if (c == null || c.kind == Cell.Kind.MISSING) missing++;
                else if (c.kind == Cell.Kind.VOID) voids++;
            }
        int solids = 1024 - missing - voids;
        double missingFrac = missing / 1024.0;
        double voidFrac = voids / 1024.0;

        if (solids < 1024 * lowDataThreshold) {
            return voids > missing
                    ? RegionInfo.impossible(coord, voidFrac, missingFrac, solids)
                    : RegionInfo.lowData(coord, voidFrac, missingFrac, solids);
        }

        Double traversal = regionTraversalCost(grid);
        if (traversal == null) {
            return RegionInfo.impossible(coord, voidFrac, missingFrac, solids);
        }

        double totalDelta = 0;
        int edges = 0;
        for (int ci = 0; ci < 32; ci++) {
            for (int cj = 0; cj < 32; cj++) {
                if (grid[ci][cj].kind != Cell.Kind.SOLID) continue;
                int h0 = grid[ci][cj].y;
                for (int[] d : new int[][]{{1, 0}, {0, 1}}) {
                    int ni = ci + d[0], nj = cj + d[1];
                    if (ni >= 32 || nj >= 32) continue;
                    if (grid[ni][nj].kind != Cell.Kind.SOLID) continue;
                    totalDelta += Math.abs(h0 - grid[ni][nj].y);
                    edges++;
                }
            }
        }
        double avgDelta = edges > 0 ? totalDelta / edges : 0;

        List<String> biomes = new ArrayList<>();
        for (Cell[] row : grid)
            for (Cell c : row)
                if (c != null && c.biome != null) biomes.add(c.biome);
        double biomeFactor = biomes.isEmpty() ? 1.0
                : biomes.stream().mapToDouble(b -> BIOME_COST.getOrDefault(b, DEFAULT_BIOME_COST))
                .average().orElse(1.0);

        double perCell = traversal / 32.0;
        double cost = perCell * (1.0 + voidPenalty * voidFrac) * biomeFactor;

        return new RegionInfo(coord, true, cost, voidFrac, missingFrac, solids, avgDelta);
    }

    private Double regionTraversalCost(Cell[][] grid) {
        Double we = axisCost(grid, true);
        Double ns = axisCost(grid, false);
        if (we == null && ns == null) return null;
        if (we == null) return ns;
        if (ns == null) return we;
        return (we + ns) / 2.0;
    }

    private Double axisCost(Cell[][] grid, boolean westEast) {
        record Node(int ci, int cj, double cost) {
        }
        PriorityQueue<Node> heap = new PriorityQueue<>(Comparator.comparingDouble(n -> n.cost));
        Map<Long, Double> g = new HashMap<>();

        for (int k = 0; k < 32; k++) {
            int ci = westEast ? 0 : k;
            int cj = westEast ? k : 0;
            Integer h = grid[ci][cj].height();
            if (h == null) continue;
            long key = ((long) ci << 32) | (cj & 0xFFFFFFFFL);
            g.put(key, 0.0);
            heap.add(new Node(ci, cj, 0.0));
        }
        if (heap.isEmpty()) return null;

        while (!heap.isEmpty()) {
            Node cur = heap.poll();
            long key = ((long) cur.ci << 32) | (cur.cj & 0xFFFFFFFFL);
            if (cur.cost > g.getOrDefault(key, Double.POSITIVE_INFINITY)) continue;
            boolean goal = westEast ? cur.ci == 31 : cur.cj == 31;
            if (goal) return cur.cost;

            Integer h0 = grid[cur.ci][cur.cj].height();
            if (h0 == null) continue;

            int[][] dirs = {{1, 0}, {-1, 0}, {0, 1}, {0, -1}};
            for (int[] d : dirs) {
                int ni = cur.ci + d[0], nj = cur.cj + d[1];
                if (ni < 0 || ni >= 32 || nj < 0 || nj >= 32) continue;

                Integer h1 = grid[ni][nj].height();
                if (h1 == null) continue;

                double newCost = cur.cost + 1.0 + Math.abs(h0 - h1);
                long nkey = ((long) ni << 32) | (nj & 0xFFFFFFFFL);
                if (newCost < g.getOrDefault(nkey, Double.POSITIVE_INFINITY)) {
                    g.put(nkey, newCost);
                    heap.add(new Node(ni, nj, newCost));
                }
            }
        }
        return null;
    }
}