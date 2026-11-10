local computer = require("computer")

local http = {}

local function finishConnect(handle, timeout)
  local deadline = computer.uptime() + timeout
  while true do
    local callOk, connected, connectError = pcall(handle.finishConnect)
    if not callOk then return nil, tostring(connected) end
    if connected then return true end
    if connected == nil then return nil, tostring(connectError) end
    if computer.uptime() > deadline then return nil, "connect timeout" end
    os.sleep(0.05)
  end
end

local function readAll(handle)
  local chunks = {}
  while true do
    local callOk, chunk, readError = pcall(handle.read)
    if not callOk then return nil, tostring(chunk) end
    if not chunk then
      if readError then return nil, tostring(readError) end
      return table.concat(chunks)
    end
    if chunk == "" then
      os.sleep(0.05)
    else
      table.insert(chunks, chunk)
    end
  end
end

function http.request(internet, url, body, timeout)
  local handle, reason = internet.request(url, body)
  if not handle then return nil, reason end
  local connected, connectError = finishConnect(handle, timeout or 5)
  local response, readError
  if connected then
    response, readError = readAll(handle)
  else
    readError = connectError
  end
  handle.close()
  return response, readError
end

return http
