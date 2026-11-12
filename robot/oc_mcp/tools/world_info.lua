local computer = require("computer")
local sides = require("sides")
local json = require("oc_mcp.json")

local FACINGS = {[sides.north] = "north", [sides.south] = "south", [sides.west] = "west", [sides.east] = "east"}
local WAYPOINT_RANGE = 400

local function round(value)
  return math.floor(value + 0.5)
end

local function waypoints(navigation)
  if not navigation.findWaypoints then return nil end
  local ok, found = pcall(navigation.findWaypoints, WAYPOINT_RANGE)
  if not ok or type(found) ~= "table" then return nil end
  local result = {}
  for _, waypoint in ipairs(found) do
    local position = waypoint.position
    if type(position) == "table" and position[1] then
      table.insert(result, {label = tostring(waypoint.label or ""), dx = round(position[1]),
                            dy = round(position[2]), dz = round(position[3])})
    end
  end
  return result
end

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
      else
        info.position_error = "navigation upgrade: " .. tostring(ok and y or x)
          .. " (robot is outside the map area the upgrade was crafted with)"
      end
      local facingOk, facing = pcall(navigation.getFacing)
      if facingOk then info.facing = FACINGS[facing] end
      if not info.x then
        local found = waypoints(navigation)
        if found and #found > 0 then info.waypoints = found end
      end
    else
      info.position_error = "no navigation upgrade: position unknown"
    end
    return true, json.encodeObject(info)
  end,
}
