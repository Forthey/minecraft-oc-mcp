local function toolText(robot)
  local durability, reason = robot:toolDurability()
  if durability then return string.format("tool durability %d%%", math.floor(durability * 100 + 0.5)) end
  return tostring(reason or "no tool equipped")
end

return {
  requires = {"robot"},
  run = function(robot, args)
    local target = robot:blockName(args.side) or "the block"
    local ok, what = robot:swing(args.side, args.sneaky)
    if ok then
      if what == "block" then
        return true, "Broke " .. target .. " (" .. args.side .. "); drops went to the inventory. " .. toolText(robot) .. "."
      end
      return true, "Hit " .. tostring(what) .. " (" .. args.side .. "). " .. toolText(robot) .. "."
    end
    if what == "air" then return false, "nothing to hit on " .. args.side .. " (air)" end
    if what == "block" then
      return false, "cannot break " .. target .. " (" .. args.side .. ") with the equipped tool ("
        .. toolText(robot) .. "). Equip a suitable tool (e.g. a pickaxe for stone/furnaces) with equip."
    end
    return false, "swing " .. args.side .. " failed: " .. tostring(what)
  end,
}
