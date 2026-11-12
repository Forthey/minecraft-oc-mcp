local format = require("oc_mcp.format")

return {
  requires = {"robot", "inventory_controller"},
  run = function(robot, args)
    local block = robot:blockName(args.side)
    local header = block and ("Block: " .. block .. "\n") or ""
    local items, size = robot:storage(args.side)
    if not items then return false, header .. size end
    return true, header .. "Storage has " .. size .. " slots.\n" .. format.items(items, "Storage is empty.")
  end,
}
