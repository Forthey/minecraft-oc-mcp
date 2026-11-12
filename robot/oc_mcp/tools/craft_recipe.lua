local Robot = require("oc_mcp.robot")
local nei = require("oc_mcp.nei")

local GRID = {}
for _, slot in ipairs(Robot.CRAFT_GRID) do GRID[slot] = true end

local function sameDamage(choice, stack)
  if choice.wildcard or choice.damage == 32767 then return true end
  return math.floor(choice.damage or 0) == math.floor(stack.damage or 0)
end

local function accepts(choices, stack)
  for _, choice in ipairs(choices) do
    if choice.name == stack.name and sameDamage(choice, stack) then return true end
  end
  return false
end

local function gridCells(recipe)
  if recipe.overlay ~= "crafting" then
    return nil, "not a crafting-table recipe (category " .. tostring(recipe.name) .. "); use nei_machine_plan for machines"
  end
  local cells = {}
  for _, position in ipairs(recipe.ingredients or {}) do
    local first = position.items and position.items[1]
    if first then
      if not position.slot then return nil, "NEI did not report grid cells for this recipe" end
      table.insert(cells, {
        slot = Robot.CRAFT_GRID[position.slot],
        choices = position.items,
        perCraft = math.max(first.size or 1, 1),
        label = first.label or (first.name .. ":" .. math.floor(first.damage or 0)),
      })
    end
  end
  if #cells == 0 then return nil, "recipe has no ingredients" end
  return cells
end

local function clearGrid(robot)
  local size = robot.api.inventorySize()
  for _, gridSlot in ipairs(Robot.CRAFT_GRID) do
    for target = 1, size do
      if robot.api.count(gridSlot) == 0 then break end
      if not GRID[target] then
        robot:withSelected(gridSlot, function()
          if robot.api.count(target) == 0 or robot.api.compareTo(target) then robot.api.transferTo(target) end
        end)
      end
    end
    if robot.api.count(gridSlot) > 0 then
      return false, "no room outside the crafting grid for the items in slot " .. gridSlot
    end
  end
  return true
end

local function itemKey(stack)
  return stack.name .. ":" .. math.floor(stack.damage or 0)
end

local function richestVariant(robot, controller, cell)
  local totals, best = {}, nil
  for source = 1, robot.api.inventorySize() do
    if not GRID[source] then
      local stack = controller.getStackInInternalSlot(source)
      if stack and accepts(cell.choices, stack) then
        local key = itemKey(stack)
        totals[key] = (totals[key] or 0) + stack.size
        if not best or totals[key] > totals[best] then best = key end
      end
    end
  end
  return best
end

local function fillCell(robot, controller, cell, need)
  local variant = richestVariant(robot, controller, cell)
  for source = 1, robot.api.inventorySize() do
    if need <= 0 or not variant then break end
    if not GRID[source] then
      local stack = controller.getStackInInternalSlot(source)
      if stack and itemKey(stack) == variant then
        local before = robot.api.count(cell.slot)
        robot:withSelected(source, function()
          if before == 0 or robot.api.compareTo(cell.slot) then robot.api.transferTo(cell.slot, need) end
        end)
        need = need - (robot.api.count(cell.slot) - before)
      end
    end
  end
  return need
end

local function freeSlot(robot)
  for slot = 1, robot.api.inventorySize() do
    if not GRID[slot] and robot.api.count(slot) == 0 then return slot end
  end
end

return {
  requires = {"robot", "crafting", "inventory_controller"},
  available = function(robot)
    if robot.api.inventorySize() < 12 then
      return false, "crafting grid needs at least 12 inventory slots (one inventory upgrade)"
    end
    return nei.available(robot)
  end,
  run = function(robot, args)
    local recipe, recipeError = nei.rawRecipe(args.recipe)
    if not recipe then return false, recipeError end
    local cells, cellsError = gridCells(recipe)
    if not cells then return false, cellsError end
    for _, cell in ipairs(cells) do
      if cell.perCraft * args.count > 64 then
        return false, "count too large: slot " .. cell.slot .. " would need " .. cell.perCraft * args.count .. " items, max 64"
      end
    end

    local cleared, clearError = clearGrid(robot)
    if not cleared then return false, clearError end

    local controller = robot:component("inventory_controller")
    local missing = {}
    for _, cell in ipairs(cells) do
      local left = fillCell(robot, controller, cell, cell.perCraft * args.count)
      if left > 0 then table.insert(missing, left .. "x " .. cell.label .. " (grid slot " .. cell.slot .. ")") end
    end
    if #missing > 0 then
      return false, "not enough ingredients in the robot inventory, missing: " .. table.concat(missing, ", ")
        .. ". The grid is partly laid out; get the items and call craft_recipe again."
    end

    local resultSlot = freeSlot(robot)
    if not resultSlot then return false, "no free slot outside the crafting grid for the result" end
    if not robot:craft(args.count, resultSlot) then
      return false, "the crafting upgrade refused the recipe (NBT-specific ingredients are not supported)"
    end
    local result = controller.getStackInInternalSlot(resultSlot)
    if not result then return true, "Crafted " .. args.count .. " time(s)." end
    return true, "Crafted " .. args.count .. " time(s): slot " .. resultSlot .. " now holds "
      .. math.floor(result.size) .. "x " .. result.name .. ":" .. math.floor(result.damage or 0)
      .. (result.label and (" (" .. result.label .. ")") or "") .. "."
  end,
}
