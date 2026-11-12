local format = require("oc_mcp.format")

return {
  requires = {"robot"},
  run = function(robot)
    return true, format.items(robot:inventory(), "Robot inventory is empty.")
  end,
}
