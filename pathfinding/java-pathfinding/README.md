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

## Запуск

```bash
java -jar target/mc-pathfinding-0.1.0.jar <путь_к_миру> <X1> <Y1> <Z1> <X2> <Y2> <Z2> <Направление>
```

### Пример

```bash
java -jar target/mc-pathfinding-0.1.0.jar "/home/ivan/.minecraft/saves/Новый мир-" 276 64 -374 130 121 -36 North
```

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