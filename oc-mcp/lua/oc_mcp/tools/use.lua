return {
  requires = {"robot"},
  run = function(robot, args)
    local ok, what = robot:use(args.side, args.sneaky, args.duration)
    if not ok then return false, "use " .. args.side .. " failed: " .. tostring(what) end
    return true, "Used " .. args.side .. ": " .. tostring(what) .. "."
  end,
}
