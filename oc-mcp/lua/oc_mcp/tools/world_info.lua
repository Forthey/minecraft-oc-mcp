local computer = require("computer")
local sides = require("sides")
local json = require("oc_mcp.json")

local FACINGS = {[sides.north] = "north", [sides.south] = "south", [sides.west] = "west", [sides.east] = "east"}

return {
  run = function(robot, args)
    local info = {robot_id = computer.address()}
    if args.world_id then
      info.world_id = args.world_id
    else
      info.world_id_error = "world_id is not configured: start the bridge with --world-id"
    end
    local robotComponent = robot:component("robot")
    if robotComponent and robotComponent.name then
      local ok, name = pcall(robotComponent.name)
      if ok then info.robot_name = name end
    end
    local navigation = robot:component("navigation")
    if navigation then
      local ok, x, y, z = pcall(navigation.getPosition)
      if ok and x then
        info.x, info.y, info.z = math.floor(x), math.floor(y), math.floor(z)
      end
      local facingOk, facing = pcall(navigation.getFacing)
      if facingOk then info.facing = FACINGS[facing] end
    else
      info.position_error = "no navigation upgrade: position unknown"
    end
    return true, json.encodeObject(info)
  end,
}
