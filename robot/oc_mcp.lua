local source = debug.getinfo(1, "S").source
local root = source:match("^@?=?(.*/)[^/]*$") or "/home/"
package.path = root .. "?.lua;" .. root .. "?/init.lua;" .. package.path

local Log = require("oc_mcp.log")
local Robot = require("oc_mcp.robot")
local Registry = require("oc_mcp.registry")
local Poller = require("oc_mcp.poller")
local toolNames = require("oc_mcp.tools")

local args = {...}
local url = args[1] or "http://127.0.0.1:8765"

local log = Log.open(root .. "oc_mcp.log")
log:write("oc-mcp client starting")
print("oc-mcp starting...")

local robot = Robot.new(log)
local internet = robot:component("internet")
if not internet then
  log:write("ERROR: Internet Card is required")
  log:close()
  return
end

local registry = Registry.load(toolNames, robot, log)
print("oc-mcp polling " .. url)
Poller.new({internet = internet, url = url, log = log}):run(function(command)
  return registry:run(command, robot)
end)
