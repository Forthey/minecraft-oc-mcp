# Minecraft Pathfinding (Java)

Утилита для генерации маршрута робота OpenComputers по миру Minecraft 1.7.10.

## Требования
- **Java** 17 или выше
- **Maven** (для сборки)

## Как собрать

Откройте терминал в корневой папке проекта (там, где находится `pom.xml`) и выполните:

```bash
mvn clean package
```

На выходе `target/mc-pathfinding-0.1.0.jar` со всеми зависимостями и `Main-Class` (maven-shade-plugin).

Если Maven падает с `bad_record_mac` / `Tag mismatch` при скачивании (замечено на macOS с JDK 26), собирать на JDK 21 и TLS 1.2:

```bash
JAVA_HOME=<jdk 21> MAVEN_OPTS="-Djdk.tls.client.protocols=TLSv1.2" mvn clean package
```

## Запуск

```bash
java -jar target/mc-pathfinding-0.1.0.jar <путь_к_миру> <X1> <Y1> <Z1> <X2> <Y2> <Z2> <Направление>
```

### Пример

```bash
java -jar target/mc-pathfinding-0.1.0.jar "/home/ivan/.minecraft/saves/Новый мир-" 276 64 -374 130 121 -36 North
```

### Путь клетками (`--cells`)

```bash
java -jar target/mc-pathfinding-0.1.0.jar --cells <путь_к_миру> <X1> <Y1> <Z1> <X2> <Y2> <Z2> <Направление>
```

В stdout одна строка: JSON-массив мировых клеток `[[x,y,z],...]` от старта до цели. Без флага вывод прежний
(относительные команды).

### Подключение к адаптеру

```bash
uv run python -m adapter serve --world-id my-world \
  --pf-jar pathfinding/java/target/mc-pathfinding-0.1.0.jar \
  --pf-world "$HOME/Library/Application Support/minecraft/saves/New World" \
  [--pf-java /path/to/java17] [--long-range 32]
```

`move_to` дальше `--long-range` блоков по x или z идёт по маршруту из jar. Нужна Java 17+ (`--pf-java`, если
`java` в PATH старее).

## Зависимости

Проект использует библиотеки `jMCX` и `jNBT` для чтения NBT-файлов. Их нет в центральном репозитории Maven, поэтому их нужно собрать и установить в локальный репозиторий вручную.

Выполните эти команды в терминале:

**1. Сборка и установка `jNBT`:**
```bash
git clone https://github.com/paul-eff/jNBT.git ~/jNBT
cd ~/jNBT
mvn clean install -Dgpg.skip=true

git clone https://github.com/paul-eff/jMCX.git ~/jMCX
cd ~/jMCX
mvn clean install -Dgpg.skip=true
```
