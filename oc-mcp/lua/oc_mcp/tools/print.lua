return {
  run = function(robot, args)
    if type(args.message) ~= "string" then return false, "message is missing" end
    robot:print(args.message)
    return true, "Printed on the robot screen."
  end,
}
