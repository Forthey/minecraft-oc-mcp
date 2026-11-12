local format = {}

function format.items(items, emptyText)
  if #items == 0 then return emptyText end
  local lines = {}
  for _, item in ipairs(items) do
    local line = "slot " .. item.slot .. ": " .. item.count .. "x"
    if item.name then line = line .. " " .. item.name end
    if item.label then line = line .. " (" .. item.label .. ")" end
    table.insert(lines, line)
  end
  return table.concat(lines, "\n")
end

return format
