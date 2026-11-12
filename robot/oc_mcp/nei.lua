local nei = {}

local loaded, tools = pcall(require, "nei.tools")

local function available(robot)
  if not robot:has("nei") then return false, "missing component: nei (OC NEI Bridge mod)" end
  if not loaded then return false, "cannot load nei.tools: " .. tostring(tools) end
  return true
end

local function recipeIdHint(recipe)
  if type(recipe) == "string" and recipe:find(":") then
    return " '" .. recipe .. "' is an item id, not a recipe id: get recipe ids (like r7fbebd0471463308) from nei_recipes."
  end
  return ""
end

local function call(name, args)
  local answer = tools.call(name, args)
  if not answer.ok then
    local err = answer.error or {}
    local text = tostring(err.code) .. ": " .. tostring(err.message)
    if err.hint then text = text .. " (" .. err.hint .. ")" end
    if err.code == "UNKNOWN_RECIPE" then text = text .. recipeIdHint(args.recipe) end
    return false, text
  end
  return true, tools.json.encode(answer.result)
end

nei.available = available

function nei.rawRecipe(id)
  local ok, recipe = pcall(tools.rawRecipe, id)
  if ok then return recipe end
  if type(recipe) == "table" then
    return nil, tostring(recipe.code) .. ": " .. tostring(recipe.message) .. recipeIdHint(id)
  end
  return nil, tostring(recipe)
end

function nei.inventoryHave(robot)
  local controller = robot:component("inventory_controller")
  if not controller then return nil end
  local totals, order = {}, {}
  for slot = 1, robot.api.inventorySize() do
    local stack = controller.getStackInInternalSlot(slot)
    if stack then
      local id = stack.name .. ":" .. math.floor(stack.damage or 0)
      if not totals[id] then table.insert(order, id) totals[id] = 0 end
      totals[id] = totals[id] + stack.size
    end
  end
  local have = {}
  for _, id in ipairs(order) do table.insert(have, {item = id, n = totals[id]}) end
  return have
end

function nei.tool(name, buildArgs)
  return {
    available = available,
    run = function(robot, args)
      local toolName = type(name) == "function" and name(args) or name
      return call(toolName, buildArgs and buildArgs(args, robot) or {})
    end,
  }
end

return nei
