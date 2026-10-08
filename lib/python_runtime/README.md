MicroPython WebAssembly PyScript port from
@micropython/micropython-webassembly-pyscript 1.29.0-6 (MIT).
Upstream: https://github.com/micropython/micropython/tree/master/ports/webassembly

Worker adaptation: accept a supplied precompiled WebAssembly.Module through
instantiateWasm, disable Node file-loader and CLI detection, and remove the
shell-build assertion. All execution is server-side. The Python source and WASM
are never loaded by the browser. There is no client-supplied Python execution.
The finance.py module is shared unchanged with the CPython/MS SQL backend.
