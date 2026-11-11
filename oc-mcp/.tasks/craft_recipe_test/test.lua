local ROOT = "/Users/tozarin/Documents/lua/oc-mcp/lua/"
package.path = ROOT .. "?.lua;" .. ROOT .. "?/init.lua;" .. package.path

local inv = {}
local selected = 1
local SIZE = 16

local function same(a, b) return a and b and a.name == b.name and a.damage == b.damage end

local api = {
  inventorySize = function() return SIZE end,
  count = function(slot) return inv[slot or selected] and inv[slot or selected].size or 0 end,
  select = function(slot) if slot then selected = slot end return selected end,
  compareTo = function(slot) return same(inv[selected], inv[slot]) end,
  transferTo = function(slot, n)
    local src = inv[selected]
    if not src then return false end
    local dst = inv[slot]
    if dst and not same(src, dst) then
      inv[slot], inv[selected] = src, dst
      return true
    end
    local room = 64 - (dst and dst.size or 0)
    local moved = math.min(n or src.size, src.size, room)
    if moved <= 0 then return false end
    inv[slot] = {name = src.name, damage = src.damage, size = (dst and dst.size or 0) + moved, label = src.label}
    src.size = src.size - moved
    if src.size == 0 then inv[selected] = nil end
    return true
  end,
}

local crafted
local components = {
  robot = {},
  crafting = {craft = function(count) crafted = {count = count, slot = selected} inv[selected] = {name = "minecraft:iron_pickaxe", damage = 0, size = 1, label = "Iron Pickaxe"} return true end},
  inventory_controller = {getStackInInternalSlot = function(slot) local s = inv[slot] return s and {name = s.name, damage = s.damage, size = s.size, label = s.label} end},
  nei = {},
}

local RECIPES = {
  pick = {overlay = "crafting", name = "Shaped Crafting", ingredients = {
    {slot = 1, items = {{name = "minecraft:iron_ingot", damage = 0, size = 1, label = "Iron Ingot"}}},
    {slot = 2, items = {{name = "minecraft:iron_ingot", damage = 0, size = 1, label = "Iron Ingot"}}},
    {slot = 3, items = {{name = "minecraft:iron_ingot", damage = 0, size = 1, label = "Iron Ingot"}}},
    {slot = 5, items = {{name = "minecraft:stick", damage = 0, size = 1, label = "Stick"}}},
    {slot = 8, items = {{name = "minecraft:stick", damage = 0, size = 1, label = "Stick"}}},
  }},
  sticks = {overlay = "crafting", name = "Shaped Crafting", ingredients = {
    {slot = 1, items = {{name = "minecraft:planks", damage = 0, size = 1}, {name = "minecraft:planks", damage = 2, size = 1}}},
    {slot = 4, items = {{name = "minecraft:planks", damage = 0, size = 1}, {name = "minecraft:planks", damage = 2, size = 1}}},
  }},
  furnace = {overlay = "smelting", name = "Smelting", ingredients = {}},
}

package.preload.component = function() return {} end
package.preload.sides = function() return {front = 3, up = 1, down = 0, back = 2, left = 5, right = 4, north = 2, south = 3, west = 4, east = 5} end
package.preload.robot = function() return api end
package.preload["nei.tools"] = function()
  return {rawRecipe = function(id) if RECIPES[id] then return RECIPES[id] end error(setmetatable({code = "UNKNOWN_RECIPE", message = "unknown recipe " .. id}, {}), 0) end}
end

local Robot = require("oc_mcp.robot")
local robot = setmetatable({components = {}, api = api, log = {write = function() end}}, Robot)
function robot:component(t) return components[t] end
local tool = require("oc_mcp.tools.craft_recipe")

local function check(name, cond) print((cond and "PASS " or "FAIL ") .. name) if not cond then error("FAILED: " .. name) end end

inv = {[2] = {name = "minecraft:dirt", damage = 0, size = 5}, [13] = {name = "minecraft:iron_ingot", damage = 0, size = 3, label = "Iron Ingot"}, [14] = {name = "minecraft:stick", damage = 0, size = 4, label = "Stick"}}
selected = 4
local ok, text = tool.run(robot, {recipe = "pick", count = 1})
print(text)
check("pickaxe crafted", ok)
check("dirt moved out of grid", inv[2] == nil or inv[2].name ~= "minecraft:dirt")
check("grid laid out: ingots 1,2,3 sticks 6,10", inv[1] and inv[1].name == "minecraft:iron_ingot" and inv[6] and inv[6].name == "minecraft:stick" and inv[10] and inv[10].name == "minecraft:stick")
check("result slot outside grid", crafted.count == 1 and crafted.slot == 4)
check("selection restored", selected == 4)

inv = {[13] = {name = "minecraft:planks", damage = 2, size = 3}, [15] = {name = "minecraft:planks", damage = 0, size = 1}}
crafted = nil
ok, text = tool.run(robot, {recipe = "sticks", count = 2})
print(text)
check("ore alternatives used", ok and crafted.count == 2 and inv[1].size == 2 and inv[5].size == 2)

inv = {[13] = {name = "minecraft:iron_ingot", damage = 0, size = 1}}
ok, text = tool.run(robot, {recipe = "pick", count = 1})
print(text)
check("missing reported", not ok and text:find("Iron Ingot") ~= nil and text:find("Stick") ~= nil)

ok, text = tool.run(robot, {recipe = "furnace", count = 1})
print(text)
check("non-crafting refused", not ok and text:find("nei_machine_plan") ~= nil)

ok, text = tool.run(robot, {recipe = "nope", count = 1})
print(text)
check("unknown recipe", not ok and text:find("UNKNOWN_RECIPE") ~= nil)

inv = {}
for s = 1, 16 do inv[s] = {name = "minecraft:dirt", damage = s, size = 1} end
ok, text = tool.run(robot, {recipe = "pick", count = 1})
print(text)
check("full inventory reported", not ok and text:find("no room") ~= nil)
print("ALL OK")
