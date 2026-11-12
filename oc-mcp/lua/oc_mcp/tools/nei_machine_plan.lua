return require("oc_mcp.nei").tool("plan", function(args)
  return {side = args.side, recipe = args.recipe, times = args.times, labels = true, lang = args.lang}
end)
