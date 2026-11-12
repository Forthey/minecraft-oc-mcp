local function describe(entry)
  local parts = {entry.side .. ":"}
  if entry.name then
    local name = entry.name
    if entry.metadata and entry.metadata ~= 0 then name = name .. ":" .. math.floor(entry.metadata) end
    table.insert(parts, name)
  end
  if entry.kind then table.insert(parts, "(" .. entry.kind .. ")") end
  if entry.hardness then table.insert(parts, string.format("hardness %.1f", entry.hardness)) end
  if #parts == 1 then table.insert(parts, "unknown") end
  return table.concat(parts, " ")
end

return {
  requires = {"geolyzer"},
  run = function(robot)
    local lines = {}
    for _, entry in ipairs(robot:surroundings()) do table.insert(lines, describe(entry)) end
    return true, table.concat(lines, "\n")
  end,
}
