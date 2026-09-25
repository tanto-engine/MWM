local path = assert(os.getenv('NIOH_RESEARCH_DIR'), 'Set NIOH_RESEARCH_DIR to the repo work folder') .. '\\ce-status.txt'
local f = assert(io.open(path, 'w'))
f:write('ce_version=', tostring(getCEVersion()), '\n')
f:write('opened_pid=', tostring(getOpenedProcessID()), '\n')
f:write('prevent_debugger_detection=', tostring(getSettingsForm().CheckBox1.Checked), '\n')
f:write('debug_isDebugging_type=', type(debug_isDebugging), '\n')
if type(debug_isDebugging)=='function' then f:write('debugging=',tostring(debug_isDebugging()),'\n') end
f:write('bptExecute=', tostring(bptExecute), '\n')
f:write('bpmDebugRegister=', tostring(bpmDebugRegister), '\n')
f:close()
return 1
