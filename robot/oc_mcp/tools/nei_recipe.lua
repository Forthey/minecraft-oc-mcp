return require("oc_mcp.nei").tool("recipe", function(args)
  return {recipe = args.recipe, labels = true, lang = args.lang}
end)
