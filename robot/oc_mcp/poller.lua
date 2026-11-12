local event = require("event")
local http = require("oc_mcp.http")
local json = require("oc_mcp.json")

local Poller = {}
Poller.__index = Poller

function Poller.new(options)
  return setmetatable({
    internet = options.internet,
    url = options.url,
    delay = options.delay or 1,
    log = options.log,
    polls = 0,
  }, Poller)
end

function Poller:request(path, body)
  return http.request(self.internet, self.url .. path, body)
end

function Poller:sendResult(id, ok, text)
  local result = {id = id, ok = ok}
  if text then result[ok and "text" or "error"] = tostring(text) end
  local _, reason = self:request("/result", json.encodeObject(result))
  if reason then self.log:write("send result failed: " .. tostring(reason)) end
end

function Poller:pollOnce(handle)
  local response, reason = self:request("/poll")
  if not response then
    self.log:write("poll failed: " .. tostring(reason))
    return
  end
  self.polls = self.polls + 1
  if self.polls % 15 == 0 then self.log:write("poll ok x" .. self.polls) end
  local decoded, body = pcall(json.decode, response)
  if not decoded then
    self.log:write("bad poll response: " .. tostring(body))
    return
  end
  local command = body and body.command
  if type(command) ~= "table" or not command.id then return end
  self.log:write("command " .. command.id .. ": " .. tostring(command.type))
  local ok, text = handle(command)
  self.log:write("  -> " .. tostring(ok) .. " " .. tostring(text))
  self:sendResult(command.id, ok, text)
end

function Poller:run(handle)
  self.log:write("polling " .. self.url)
  while true do
    self:pollOnce(handle)
    event.pull(self.delay)
  end
end

return Poller
