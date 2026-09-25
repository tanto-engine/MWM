local p=assert(_freshNiohProbe)
local f=assert(io.open(assert(os.getenv('NIOH_RESEARCH_DIR'), 'Set NIOH_RESEARCH_DIR to the repo work folder') .. '\\one-shot.txt','w'))
for _,name in ipairs({'site','armed','done','read_ok','expired','error','rbx','rdi','rsi','r15','rip','previous','owner','object_bytes','previous_bytes','new_bytes','payload_bytes'}) do
  local v=p[name]
  f:write(name,'=')
  if type(v)=='table' then
    for _,b in ipairs(v) do f:write(string.format('%02X ',b)) end
  elseif type(v)=='number' then f:write(string.format('0x%X',v))
  else f:write(tostring(v)) end
  f:write('\n')
end
local bps=debug_getBreakpointList() or {}
f:write('breakpoints=',tostring(#bps),'\n')
f:close()
return p.done and 1 or 0
