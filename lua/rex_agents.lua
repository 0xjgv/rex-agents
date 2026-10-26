-- Managed by rex-agents.
-- Commands run as argument arrays; prompts live in terminals, outside action time limits.
local cli = @CLI@
local rex_binary = @REX@
local command_path = @PATH@
local function command(ctx)
  local argv = {cli}
  for _, pair in ipairs({{"--server", ctx.server}, {"--session", ctx.session_id},
                         {"--block", ctx.block_id}, {"--client", ctx.client_id}}) do
    if type(pair[2]) == "string" and pair[2] ~= "" then
      table.insert(argv, pair[1])
      table.insert(argv, pair[2])
    end
  end
  return argv
end
local function execute(argv, input)
  local result, err = rex.exec(argv, {stdin = input, timeout = 24, env = {REX_AGENTS_REX = rex_binary, PATH = command_path}})
  if result == nil then error(err, 0) end
  if not result.ok then error(result.stderr, 0) end
  if result.stdout == "" then return {} end
  return rex.json.decode(result.stdout)
end
local function perform(ctx, operation, args, prompt)
  local argv = command(ctx)
  local payload = rex.json.encode({operation = operation, args = args})
  if prompt then
    table.insert(argv, "_prompt")
    table.insert(argv, payload)
    local result, err = rex.session.new_split{
      anchor_id = ctx.block_id, direction = "horizontal", side = "after", focus = false,
      layout = rex.layout.block{
        flavor = "com.superlogical.terminal.shell",
        options = {command = argv, exit = {on_completion = false}},
      },
    }
    if err ~= nil then error(err, 0) end
    return result
  end
  table.insert(argv, "_action")
  return execute(argv, payload)
end
rex.action{
  name = "rex_agents_list", title = "List Agents", category = "Agents", args = {},
  run = function(ctx, args) return perform(ctx, "list", args, true) end,
}
rex.action{
  name = "rex_agents_send", title = "Message Agent", category = "Agents",
  args = {target = "string?", message = "string?", fyi = "boolean?", reply_to = "string?"},
  run = function(ctx, args) return perform(ctx, "send", args, not args.target or not args.message) end,
}
rex.action{
  name = "rex_agents_focus", title = "Focus Agent", category = "Agents", args = {target = "string?"},
  run = function(ctx, args) return perform(ctx, "focus", args, not args.target) end,
}
rex.action{
  name = "rex_agents_launch", title = "Launch Agent", category = "Agents",
  args = {kind = "string?", name = "string?", cwd = "string?", task = "string?", host = "string?"},
  run = function(ctx, args)
    return perform(ctx, "launch", args, not args.kind or not args.name or not args.cwd)
  end,
}
rex.action{
  name = "rex_agents_registry", title = "Export Agent Locations", category = "Agents", args = {},
  run = function() return execute({cli, "_registry"}) end,
}
rex.action{
  name = "rex_agents_remote_launch", title = "Launch Agent on This Host", category = "Agents",
  args = {kind = "string", name = "string", cwd = "string", task = "string?"},
  run = function(_, args)
    return execute({cli, "_action"}, rex.json.encode({operation = "launch", args = args}))
  end,
}

rex.action{
  name = "rex_agents_navigation", title = "Toggle Agent Navigation", category = "Agents",
  args = {mode = "string?"},
  run = function(ctx, args) return perform(ctx, "navigation", args, false) end,
}
