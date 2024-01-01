import re


def main():
    with open('webgl.idl') as fp:
        x = fp.read()

    x = re.sub(r'//.*\n', '', x)
    x = re.sub(r'/\*.*\*/', '', x)
    x = re.sub(r'\[[^]]*\]', '', x)
    x = re.sub(r'\([^\)]*\)', '()', x)
    x = re.sub(r'typedef[^;]*;', '', x)

    with open('webgl.py', 'w') as fp:
        fp.write("""
# AUTOGENERATED FILE -- DO NOT EDIT -- See parse_idl.py
#
# WebGL IDL definitions scraped from the Khronos specification:
# https://www.khronos.org/registry/webgl/specs/latest/
                 
from typing import Any, Optional                 
from abc import ABC, abstractmethod


INTERFACES = {}


def register(cls):
    INTERFACES[cls.__name__] = cls
    return cls


class ProxyInterfaceBase(ABC):
    @abstractmethod
    def _get_attribute(self, name) -> Any: NotImplemented
    @abstractmethod
    def _set_attribute(self, name, value) -> None: NotImplemented
    @abstractmethod
    def _invoke_function(self, name, *args) -> Any: NotImplemented
    @abstractmethod
    def _invoke_procedure(self, name, *args) -> None: NotImplemented
""")

        interfaces = set()
        for m in re.finditer(r'interface\s+(?:mixin\s+)?(\S+)\s*(?::\s+(\S+)\s*)?\{([^\}]*)\}', x):
            interface = m.group(1)
            parent_interface = m.group(2)
            if interface not in ("WebGLUniformLocation", "WebGLRenderingContextBase", "WebGLRenderingContextOverloads", "WebGLObject") and parent_interface != "WebGLObject":
                continue

            fp.write("\n\n")

            body = m.group(3)
            fp.write("@register\n")
            if parent_interface:
                fp.write(f"class {interface}({parent_interface}): \n")
            else:
                fp.write(f"class {interface}(ProxyInterfaceBase):\n")
            has_decl = False
            funcs = set()
            interfaces.add(interface)
            for decl in body.split(';'):
                decl = decl.strip()
                if decl:
                    has_decl = True
                    s = decl.split()
                    if "const" in s:
                        x, _, z = decl.partition("=")
                        x = x.strip().split()
                        z = z.strip()
                        fp.write(f"    {x[-1]} = {z}\n")
                    elif "attribute" in s:
                        x, _, _ = decl.partition("=")
                        attr = x.split()[-1]
                        fp.write("    @property\n")
                        fp.write(f"    def {attr}(self): return self._get_attribute(\"{attr}\")\n")
                        if "readonly" not in s:
                            fp.write(f"    @{attr}.setter\n")
                            fp.write(f"    def {attr}(self, value): self._set_attribute(\"{attr}\", value)\n")
                    elif "()" in decl:
                        x = decl.replace('()', '').split()
                        func = x[-1]
                        if func in funcs:
                            continue
                        return_type = x[0]
                        optional = False
                        if return_type.endswith('?'):
                            optional = True
                            return_type = return_type[:-1]
                        if 'undefined' in x:
                            fp.write(f'    def {func}(self, *args) -> None: self._invoke_procedure(\"{func}\", *args)\n')
                        elif return_type in interfaces:
                            if optional:
                                return_type = f"Optional[{return_type}]"
                            fp.write(f'    def {func}(self, *args) -> {return_type}: return self._invoke_function(\"{func}\", *args)\n')
                        else:
                            fp.write(f'    def {func}(self, *args) -> Any: return self._invoke_function(\"{func}\", *args)\n')
                        funcs.add(func)
                    else:
                        raise ValueError(decl)
            if not has_decl:
                fp.write("    pass\n")


if __name__ == "__main__":
    main()
