local function durabilityText(robot)
  local durability = robot:toolDurability()
  if not durability then return "" end
  return string.format(" Tool durability: %d%%.", math.floor(durability * 100 + 0.5))
end

return {
  requires = {"robot"},
  run = function(robot, args)
    local ok, what = robot:swing(args.side, args.sneaky)
    if not ok then return false, "swing " .. args.side .. " failed: " .. tostring(what) end
    return true, "Swung " .. args.side .. ", hit: " .. tostring(what) .. "." .. durabilityText(robot)
  end,
}
