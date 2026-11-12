return {
  requires = {"robot"},
  run = function(robot, args)
    local n = args.n or 1
    local moved, reason = robot:move(args.direction, n)
    if moved < n then
      return false, "moved " .. moved .. " of " .. n .. " blocks " .. args.direction .. ", blocked: " .. tostring(reason)
    end
    return true, "Moved " .. args.direction .. " " .. n .. " blocks."
  end,
}
