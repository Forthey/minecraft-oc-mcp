return {
  requires = {"robot"},
  run = function(robot, args)
    local slot = args.slot or robot.api.select()
    if robot.api.count(slot) == 0 then
      return false, "slot " .. slot .. " is empty, nothing to place"
    end
    local occupied = robot:blockName(args.side)
    local placed, reason = robot:place(args.side, args.slot, args.sneaky)
    if not placed then
      local why = tostring(reason or "unknown reason")
      if occupied and occupied ~= "minecraft:air" then
        why = why .. "; " .. args.side .. " is occupied by " .. occupied .. " (break it with swing first)"
      end
      return false, "cannot place from slot " .. slot .. " " .. args.side .. ": " .. why
    end
    local now = robot:blockName(args.side)
    return true, "Placed from slot " .. slot .. " " .. args.side .. (now and (": " .. now) or "") ..
      ". " .. robot.api.count(slot) .. " left in slot " .. slot .. "."
  end,
}
