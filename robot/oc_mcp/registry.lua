local Registry = {}
Registry.__index = Registry

local function checkRequirements(tool, robot)
  for _, componentType in ipairs(tool.requires or {}) do
    if not robot:has(componentType) then return false, "missing component: " .. componentType end
  end
  if tool.available then return tool.available(robot) end
  return true
end

function Registry.load(names, robot, log)
  local self = setmetatable({tools = {}, disabled = {}}, Registry)
  for _, name in ipairs(names) do
    local loaded, tool = pcall(require, "oc_mcp.tools." .. name)
    local enabled, reason
    if not loaded then
      enabled, reason = false, "load error: " .. tostring(tool)
    else
      enabled, reason = checkRequirements(tool, robot)
    end
    if enabled then
      self.tools[name] = tool
      log:write("tool " .. name .. ": enabled")
    else
      self.disabled[name] = reason or "unavailable"
      log:write("tool " .. name .. ": disabled (" .. self.disabled[name] .. ")")
    end
  end
  return self
end

function Registry:run(command, robot)
  local name = command.type
  local tool = self.tools[name]
  if not tool then
    if self.disabled[name] then return false, "tool " .. name .. " is disabled: " .. self.disabled[name] end
    return false, "unknown command type: " .. tostring(name)
  end
  local callOk, ok, text = pcall(tool.run, robot, command)
  if not callOk then return false, tostring(ok) end
  return ok, text
end

return Registry
