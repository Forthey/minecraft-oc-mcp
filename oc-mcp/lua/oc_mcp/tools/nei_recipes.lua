return require("oc_mcp.nei").tool(function(args)
  return args.usages and "usages" or "recipes"
end, function(args)
  return {item = args.item, category = args.category, limit = args.limit, cursor = args.cursor, labels = true, lang = args.lang}
end)
