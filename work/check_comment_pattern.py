import sys
sys.path.insert(0,'work/auditdeps')
import importlib
for module in ('lupa.lua51','lupa.lua52','lupa.lua53','lupa.lua54','lupa.lua55'):
    lua=importlib.import_module(module).LuaRuntime(unpack_returned_tuples=True)
    sample='before<!--comment-->after'
    call=lua.eval('function(s,p) return s:gsub(p, "") end')
    print(lua.eval('_VERSION'),repr(call(sample,'<!--.-?-->')))
