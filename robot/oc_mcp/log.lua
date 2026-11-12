local Log = {}
Log.__index = Log

function Log.open(path)
  return setmetatable({file = assert(io.open(path, "w"))}, Log)
end

function Log:write(message)
  self.file:write(tostring(message) .. "\n")
  self.file:flush()
end

function Log:close()
  self.file:close()
end

return Log
