local component = require("component")
local sides = require("sides")

local Robot = {}
Robot.__index = Robot

local SIDES = {front = sides.front, up = sides.up, down = sides.down}
local ALL_SIDES = {"front", "back", "left", "right", "up", "down"}
local DROPS = {front = "drop", up = "dropUp", down = "dropDown"}
local TURNS = {left = "turnLeft", right = "turnRight", around = "turnAround"}
local MOVES = {forward = "forward", back = "back", up = "up", down = "down"}

local function proxyOf(componentType)
  local address = component.list(componentType)()
  return address and component.proxy(address) or nil
end

function Robot.new(log)
  local self = setmetatable({log = log, components = {}}, Robot)
  for address, componentType in component.list() do
    log:write("component " .. componentType .. " " .. address)
  end
  if self:has("robot") then self.api = require("robot") end
  return self
end

function Robot:component(componentType)
  if self.components[componentType] == nil then
    self.components[componentType] = proxyOf(componentType) or false
  end
  return self.components[componentType] or nil
end

function Robot:has(componentType)
  return self:component(componentType) ~= nil
end


function Robot:move(direction, n)
  local step = MOVES[direction] and self.api[MOVES[direction]]
  if not step then error("unknown direction: " .. tostring(direction)) end
  for done = 0, n - 1 do
    local moved, reason = step()
    if not moved then return done, reason end
  end
  return n
end

function Robot:turn(direction)
  local turn = TURNS[direction] and self.api[TURNS[direction]]
  if not turn then error("unknown direction: " .. tostring(direction)) end
  return turn()
end

function Robot:side(name)
  local side = SIDES[name or "front"]
  if not side then error("unknown side: " .. tostring(name)) end
  return side
end

function Robot:withSelected(slot, action)
  if not slot then return action() end
  local previous = self.api.select()
  self.api.select(slot)
  local result = table.pack(pcall(action))
  self.api.select(previous)
  if not result[1] then error(result[2], 0) end
  return table.unpack(result, 2, result.n)
end

local function describe(slot, count, stack)
  return {slot = slot, count = count, name = stack and stack.name, label = stack and stack.label}
end

function Robot:inventory()
  local controller = self:component("inventory_controller")
  local items = {}
  for slot = 1, self.api.inventorySize() do
    local count = self.api.count(slot)
    if count > 0 then
      table.insert(items, describe(slot, count, controller and controller.getStackInInternalSlot(slot)))
    end
  end
  return items
end

function Robot:transfer(fromSlot, toSlot, count)
  if self.api.count(fromSlot) == 0 then return false, "slot " .. fromSlot .. " is empty" end
  return self:withSelected(fromSlot, function()
    if self.api.count(toSlot) > 0 and not self.api.compareTo(toSlot) then
      return false, "slot " .. toSlot .. " holds a different item"
    end
    if not self.api.transferTo(toSlot, count) then
      return false, "slot " .. toSlot .. " is full"
    end
    return true
  end)
end

function Robot:surroundings()
  local geolyzer = self:component("geolyzer")
  local robotComponent = self:component("robot")
  local result = {}
  for _, name in ipairs(ALL_SIDES) do
    local entry = {side = name}
    if robotComponent and SIDES[name] then
      local ok, _, kind = pcall(robotComponent.detect, sides[name])
      if ok then entry.kind = kind end
    end
    if geolyzer then
      local ok, block = pcall(geolyzer.analyze, sides[name])
      if ok and type(block) == "table" then
        entry.name = block.name
        entry.metadata = block.metadata
        entry.hardness = block.hardness
      end
    end
    table.insert(result, entry)
  end
  return result
end

local AXES = {
  [sides.north] = {forward = {0, -1}, right = {1, 0}},
  [sides.south] = {forward = {0, 1}, right = {-1, 0}},
  [sides.west] = {forward = {-1, 0}, right = {0, -1}},
  [sides.east] = {forward = {1, 0}, right = {0, 1}},
}

function Robot:axes()
  local navigation = self:component("navigation")
  if not navigation then return nil end
  local ok, facing = pcall(navigation.getFacing)
  return ok and AXES[facing] or nil
end

function Robot:geoScan(x, z, y, width, depth, height)
  local geolyzer = self:component("geolyzer")
  return geolyzer.scan(x, z, y, width, depth, height)
end

function Robot:blockName(sideName)
  local geolyzer = self:component("geolyzer")
  if not geolyzer then return nil end
  local ok, block = pcall(geolyzer.analyze, self:side(sideName))
  if not ok or type(block) ~= "table" or not block.name then return nil end
  if block.metadata and block.metadata ~= 0 then
    return block.name .. ":" .. math.floor(block.metadata)
  end
  return block.name
end

function Robot:storage(sideName)
  local controller = self:component("inventory_controller")
  local side = self:side(sideName)
  local size = controller.getInventorySize(side)
  if not size then return nil, "no storage on side " .. tostring(sideName or "front") end
  local items = {}
  for slot = 1, size do
    local stack = controller.getStackInSlot(side, slot)
    if stack then table.insert(items, describe(slot, stack.size, stack)) end
  end
  return items, size
end

function Robot:take(sideName, slot, count, robotSlot)
  local controller = self:component("inventory_controller")
  local side = self:side(sideName)
  return self:withSelected(robotSlot, function()
    return controller.suckFromSlot(side, slot, count or 64)
  end)
end

function Robot:put(sideName, robotSlot, count, slot)
  local side = self:side(sideName)
  return self:withSelected(robotSlot, function()
    if slot then
      return self:component("inventory_controller").dropIntoSlot(side, slot, count)
    end
    return self.api[DROPS[sideName or "front"]](count)
  end)
end

function Robot:swing(sideName, sneaky)
  return self:component("robot").swing(self:side(sideName), nil, sneaky)
end

function Robot:use(sideName, sneaky, duration)
  return self:component("robot").use(self:side(sideName), nil, sneaky, duration)
end

function Robot:equip(slot)
  local controller = self:component("inventory_controller")
  return self:withSelected(slot, function()
    return controller.equip()
  end)
end

function Robot:toolDurability()
  return self:component("robot").durability()
end

Robot.CRAFT_GRID = {1, 2, 3, 5, 6, 7, 9, 10, 11}

function Robot:craftGrid()
  local controller = self:component("inventory_controller")
  local grid = {}
  for position, slot in ipairs(Robot.CRAFT_GRID) do
    local count = self.api.count(slot)
    if count > 0 then
      local stack = controller and controller.getStackInInternalSlot(slot)
      grid[position] = {slot = slot, count = count, name = stack and stack.name}
    end
  end
  return grid
end

function Robot:craft(count, resultSlot)
  local crafting = self:component("crafting")
  return self:withSelected(resultSlot, function()
    return crafting.craft(count)
  end)
end

return Robot
