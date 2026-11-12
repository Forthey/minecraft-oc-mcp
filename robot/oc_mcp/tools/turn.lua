return {
  requires = {"robot"},
  run = function(robot, args)
    local turned, reason = robot:turn(args.direction)
    if not turned then return false, "turn failed: " .. tostring(reason) end
    return true, "Turned " .. args.direction .. "."
  end,
}
