local Robot = require("oc_mcp.robot")

local function isGridSlot(slot)
  for _, gridSlot in ipairs(Robot.CRAFT_GRID) do
    if gridSlot == slot then return true end
  end
  return false
end

local function describeGrid(grid)
  local rows = {}
  for row = 0, 2 do
    local cells = {}
    for column = 1, 3 do
      local position = row * 3 + column
      local cell = grid[position]
      local slot = Robot.CRAFT_GRID[position]
      table.insert(cells, "[" .. slot .. ": " .. (cell and (cell.count .. "x " .. (cell.name or "?")) or "empty") .. "]")
    end
    table.insert(rows, table.concat(cells, " "))
  end
  return table.concat(rows, "\n")
end

return {
  requires = {"robot", "crafting"},
  available = function(robot)
    if robot.api.inventorySize() < 12 then
      return false, "crafting grid needs at least 12 inventory slots (one inventory upgrade)"
    end
    return true
  end,
  run = function(robot, args)
    if args.result_slot and isGridSlot(args.result_slot) then
      return false, "result_slot " .. args.result_slot .. " is inside the crafting grid, use 4, 8, 12 or 13+"
    end
    local grid = robot:craftGrid()
    if next(grid) == nil then
      return false, "crafting grid is empty (grid slots are 1,2,3 / 5,6,7 / 9,10,11)"
    end
    local crafted = robot:craft(args.count, args.result_slot)
    if not crafted then
      return false, "no recipe matches the grid, or there is no free slot for the result. Current grid:\n"
        .. describeGrid(grid)
    end
    return true, "Crafted. Use inventory_scan to see the result."
  end,
}
