return {
  requires = {"robot", "inventory_controller"},
  run = function(robot, args)
    if not robot:equip(args.slot) then return false, "cannot equip from slot " .. args.slot end
    return true, "Swapped slot " .. args.slot .. " with the tool slot."
  end,
}
