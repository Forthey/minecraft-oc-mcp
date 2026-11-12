local MAX_VOLUME = 64

local function cell(value)
  if value == nil then return "?" end
  if value == 0 then return "." end
  return string.format("%.1f", value)
end

local function worldBox(axes, x, z, width, depth)
  local minX, minZ, maxX, maxZ = math.huge, math.huge, -math.huge, -math.huge
  for _, r in ipairs({x, x + width - 1}) do
    for _, f in ipairs({z, z + depth - 1}) do
      local wx = r * axes.right[1] + f * axes.forward[1]
      local wz = r * axes.right[2] + f * axes.forward[2]
      minX, maxX = math.min(minX, wx), math.max(maxX, wx)
      minZ, maxZ = math.min(minZ, wz), math.max(maxZ, wz)
    end
  end
  return minX, minZ, maxX - minX + 1, maxZ - minZ + 1
end

return {
  requires = {"geolyzer"},
  run = function(robot, args)
    local x, z, y = args.x, args.z, args.y
    local width, depth, height = args.width, args.depth, args.height
    if width * depth * height > MAX_VOLUME then
      return false, "width*depth*height must be <= " .. MAX_VOLUME
    end
    local axes = robot:axes()
    local scanX, scanZ, scanWidth, scanDepth = x, z, width, depth
    if axes then scanX, scanZ, scanWidth, scanDepth = worldBox(axes, x, z, width, depth) end
    local ok, data = pcall(robot.geoScan, robot, scanX, scanZ, y, scanWidth, scanDepth, height)
    if not ok or type(data) ~= "table" then return false, "scan failed: " .. tostring(data) end

    local xName, zName = "east", "south"
    if axes then xName, zName = "right", "forward" end
    local lines = {"axes: x = " .. xName .. ", z = " .. zName .. ", y = up"}
    for dy = 0, height - 1 do
      table.insert(lines, "y=" .. (y + dy) .. " (rows z=" .. z .. ".." .. (z + depth - 1)
        .. ", columns x=" .. x .. ".." .. (x + width - 1) .. "):")
      for dz = 0, depth - 1 do
        local row = {}
        for dx = 0, width - 1 do
          local wx, wz = x + dx, z + dz
          if axes then
            wx = (x + dx) * axes.right[1] + (z + dz) * axes.forward[1]
            wz = (x + dx) * axes.right[2] + (z + dz) * axes.forward[2]
          end
          local index = 1 + (wx - scanX) + (wz - scanZ) * scanWidth + dy * scanWidth * scanDepth
          table.insert(row, cell(data[index]))
        end
        table.insert(lines, table.concat(row, " "))
      end
    end
    return true, table.concat(lines, "\n")
  end,
}
