from MacroPlanner import MacroPlanner
from RegionEstimater import RegionCostEstimator
from RegionCoord import RegionCoord

WORLD = "/home/ivan/.minecraft/saves/Новый мир-"

estimator = RegionCostEstimator(WORLD)

start = (-71, 102, 152)
goal  = (-2020, 64, 1782)
estimator.debug(RegionCoord.from_world(start[0], start[2]))
estimator.debug(RegionCoord.from_world(goal[0],  goal[2]))

planner = MacroPlanner(estimator)
route = planner.plan(start_xyz=start, goal_xyz=goal)

print(f"\nМаршрут: {len(route)} регионов")
for r in route:
    info = estimator.estimate(r)
    print(
        f"({r.x:>3},{r.z:>3}) "
        f"exists={info.exists} "
        f"cost={info.cost_factor:>6.2f} "
        f"void={info.void_fraction:.1%} "
        f"miss={info.missing_fraction:.1%} "
        f"avg_dh={info.avg_delta:.1f} "
        f"solids={info.samples_count}"
    )