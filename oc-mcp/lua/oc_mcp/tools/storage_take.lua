return {
  requires = {"robot", "inventory_controller"},
  run = function(robot, args)
    local taken, reason = robot:take(args.side, args.slot, args.count, args.robot_slot)
    if not taken or taken == 0 then
      return false, "cannot take items from " .. args.side .. " slot " .. args.slot .. ": " .. tostring(reason)
    end
    return true, "Took items from " .. args.side .. " slot " .. args.slot .. "."
  end,
}
