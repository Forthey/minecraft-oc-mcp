return {
  requires = {"robot"},
  run = function(robot, args)
    local moved, reason = robot:transfer(args.from_slot, args.to_slot, args.count)
    if not moved then
      return false, "cannot move items from slot " .. args.from_slot .. " to slot " .. args.to_slot
        .. ": " .. tostring(reason)
    end
    return true, "Moved items from slot " .. args.from_slot .. " to slot " .. args.to_slot .. "."
  end,
}
