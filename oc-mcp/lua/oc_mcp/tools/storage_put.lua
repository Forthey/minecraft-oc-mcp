return {
  requires = {"robot"},
  run = function(robot, args)
    if args.slot and not robot:has("inventory_controller") then
      return false, "putting into a specific slot requires an inventory controller"
    end
    local put, reason = robot:put(args.side, args.robot_slot, args.count, args.slot)
    if not put or put == 0 then
      return false, "cannot put items " .. args.side .. ": " .. tostring(reason)
    end
    return true, "Put items from robot slot " .. args.robot_slot .. " " .. args.side .. "."
  end,
}
