return require("oc_mcp.nei").tool("find", function(args)
  return {text = args.text, limit = args.limit, lang = args.lang}
end)
