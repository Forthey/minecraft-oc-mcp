local json = {}

local escapes = {n = "\n", r = "\r", t = "\t", b = "\b", f = "\f", ['"'] = '"', ["\\"] = "\\", ["/"] = "/"}

function json.encodeString(value)
  value = value:gsub("\\", "\\\\"):gsub('"', '\\"'):gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t")
  return '"' .. value .. '"'
end

function json.encodeObject(object)
  local parts = {}
  for key, value in pairs(object) do
    local encoded
    if type(value) == "string" then
      encoded = json.encodeString(value)
    else
      encoded = tostring(value)
    end
    table.insert(parts, json.encodeString(key) .. ":" .. encoded)
  end
  return "{" .. table.concat(parts, ",") .. "}"
end

local function skipSpaces(text, position)
  return text:find("[^%s]", position) or #text + 1
end

local function decodeString(text, position)
  local result = {}
  position = position + 1
  while position <= #text do
    local char = text:sub(position, position)
    if char == '"' then return table.concat(result), position + 1 end
    if char == "\\" then
      local escaped = text:sub(position + 1, position + 1)
      table.insert(result, escapes[escaped] or escaped)
      position = position + 2
    else
      table.insert(result, char)
      position = position + 1
    end
  end
  error("unterminated JSON string")
end

local function decodeScalar(text, position)
  local char = text:sub(position, position)
  if char == '"' then return decodeString(text, position) end
  for literal, value in pairs({["true"] = true, ["false"] = false, ["null"] = json.null}) do
    if text:sub(position, position + #literal - 1) == literal then
      return value, position + #literal
    end
  end
  local number = text:match("^-?%d+%.?%d*[eE]?[-+]?%d*", position)
  if number and number ~= "" then return tonumber(number), position + #number end
  error("unsupported JSON value at " .. position)
end

local function decodeObject(text, position)
  local object = {}
  position = skipSpaces(text, position + 1)
  if text:sub(position, position) == "}" then return object, position + 1 end
  while true do
    if text:sub(position, position) ~= '"' then error("expected key at " .. position) end
    local key
    key, position = decodeString(text, position)
    position = skipSpaces(text, position)
    if text:sub(position, position) ~= ":" then error("expected ':' at " .. position) end
    local value
    value, position = json.decodeValue(text, skipSpaces(text, position + 1))
    if value ~= json.null then object[key] = value end
    position = skipSpaces(text, position)
    local char = text:sub(position, position)
    if char == "}" then return object, position + 1 end
    if char ~= "," then error("expected ',' or '}' at " .. position) end
    position = skipSpaces(text, position + 1)
  end
end

json.null = setmetatable({}, {__tostring = function() return "null" end})

function json.decodeValue(text, position)
  if text:sub(position, position) == "{" then return decodeObject(text, position) end
  return decodeScalar(text, position)
end

function json.decode(text)
  local value = json.decodeValue(text, skipSpaces(text, 1))
  if value == json.null then return nil end
  return value
end

return json
