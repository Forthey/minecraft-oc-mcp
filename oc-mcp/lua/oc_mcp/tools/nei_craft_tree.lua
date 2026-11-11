local nei = require("oc_mcp.nei")

return nei.tool("craft", function(args, robot)
  local have = args.use_inventory and nei.inventoryHave(robot) or nil
  return {item = args.item, count = args.count, have = have, labels = true, lang = args.lang}
end)
