from collections import defaultdict
import pathlib, sys
from dataclasses import dataclass
from tree_sitter import Node, Parser, Language
from tree_sitter_go import language as golang

@dataclass
class Method:
    name: str
    params: list[str]
    returns: list[str]

@dataclass
class Interface:
    name: str
    methods: list[Method]

@dataclass
class Struct:
    name: str
    fields: dict[str, str]
    embedded: list[str]
    methods: list[Method]

@dataclass(frozen=True)
class Node:
    name: str
    type: Interface | Struct

class CodeParser:
    def __init__(self, srcDir: str, debug = False):
        self.debug = debug
        self.srcDir = srcDir
        self.language = Language(golang())
        self.parser = Parser()
        self.parser.language = self.language
        self.interfaces: dict[str, list[Method]] = defaultdict(list)
        self.structs: dict[str, Struct] = {}


    def extract_data(self):
        self.parse_dir()
        if self.debug:
            print('========== interfaces ============')
            for i, v in g.interfaces.items():
                print(i)
                for m in v:
                    print('\t', m)
            print('========== structs ============')
            for s in g.structs.values():
                print(s.name)
                for fname, ftype in s.fields.items():
                    print('\t', fname, '\t()', ftype, sep='')
                print()
                for m in s.methods:
                    print('\t', m, sep='')

        interfaces: dict[str, Interface] = {}

        for name, methods in self.interfaces.items():
            interfaces[name] = Interface(name, methods)

        return interfaces, self.structs


    def parse_dir(self):
        for file in pathlib.Path(self.srcDir).rglob("*.go"):
            src = open(file, 'r', encoding='utf-8').read()
            tree = self.parser.parse(bytes(src, 'utf8'))

            self.extract_interafces(tree.root_node)
            self.extract_structs(tree.root_node)
            self.extract_struct_methods(tree.root_node)

    def normalize_named_params(self, params: str):
        results: list[str] = []
        params = params.strip('()')
        if params:
            for part in params.split(','):
                part = part.strip()
                if part:
                    splitted = part.split(' ', 1)
                    results.append(splitted[0] if len(splitted) ==  1 else ''.join(splitted[1:]))
        return results

    def extract_interafces(self, node: Node):
        query = self.language.query('''
            (type_declaration
              (type_spec
                name: (type_identifier) @name
                type: (interface_type) @interface
              ) @spec)
        ''')
        captures = query.captures(node)
        for i in range(len(captures.get('spec', []))):
            node = captures['spec'][i]
            name = node.child_by_field_name('name')
            body = node.child_by_field_name('type')
            if name and name.text: name = name.text.decode()
            if not body or not body.children or not name: return
            for method in body.children:
                if method.type == 'method_elem':
                    method = self.parse_interface_methods(method)
                    self.interfaces[name].append(method)

    def parse_interface_methods(self, node: Node) -> Method:
        method = {}
        for child in node.children:
            if child.type == 'field_identifier':
                method['name'] = child.text.decode()
            elif child.type == 'parameter_list':
                method['returns' if 'params' in method else 'params'] = child.text.decode()
            elif child.type == 'type_identifier':
                method['returns'] = f'({child.text.decode()})'
        return Method(
            name=method['name'],
            params=self.normalize_named_params(method['params']),
            returns=self.normalize_named_params(method['returns']) if 'returns' in method else []
        )

    def extract_structs(self, node: Node):
        query = self.language.query('''
            (type_declaration
                (type_spec
                    name: (type_identifier) @name
                    type: (struct_type(field_declaration_list) @list)
                ) @spec
            )
        ''')
        captures = query.captures(node)
        for i in range(len(captures.get('spec', []))):
            spec = captures['spec'][i]
            name = spec.child_by_field_name('name').text.decode()
            assert(name != None)
            for child in spec.children:
                if child.type == 'struct_type':
                    curr = child
                    for child in curr.children:
                        if child.type == 'field_declaration_list':
                            curr = child
                            fields, embedded = {}, []
                            for child in curr.children:
                                if child.type == 'field_declaration':
                                    fname = child.child_by_field_name('name')
                                    tname = child.child_by_field_name('type').text.decode()
                                    if fname:
                                        fields[fname.text.decode()] = tname
                                    else:
                                        embedded.append(tname)
                            self.structs[name] = Struct(name=name, fields=fields, embedded=embedded, methods=[])

    def extract_struct_methods(self, node):
        query = self.language.query('''
            (method_declaration
               	receiver: (parameter_list
                    (parameter_declaration
                        type: [
                            (type_identifier) @recv
                            (pointer_type (type_identifier) @recv)
                        ]))
                name: (field_identifier) @name
                parameters: (parameter_list) @params
                result: (_)? @returns)
            ''')
        captures = query.captures(node)
        for i in range(len(captures.get('name', []))):
            name = captures['name'][i].text.decode()
            recv = captures['recv'][i].text.decode()
            params = captures['params'][i].text.decode()

            returns = '()'
            if 'returns' in captures and len(captures['returns']) > i:
                returns = captures['returns'][i].text.decode()
                returns = returns if returns.startswith('(') else f'({returns})'
            assert(recv in self.structs)
            self.structs[recv].methods.append(Method(
                name=name,
                params= self.normalize_named_params(params),
                returns=self.normalize_named_params(returns)
            ))



class GraphBuilder:
    def __init__(self, interfaces: dict[str, Interface], structs: dict[str, Struct]):
        self.interfaces = interfaces
        self.structs = structs
        self.graph: dict[Node, list[Node]] = defaultdict(list)

    def resolve_interface_implementations(self):
        for struct in self.structs.values():
            for interface in self.interfaces.values():
                if self.does_implement(struct, interface):
                    print(f'{struct.name} IMPLEMENTS {interface.name}')
                    self.graph[Node(name=interface.name, type=Interface)].append(
                        Node(name=struct.name, type=Struct)
                    )

    def does_implement(self, struct: Struct, interface: Interface):
        # TODO: add methods from embedded structs
        if not struct.methods: return False
        return all(item in interface.methods for item in struct.methods)

if __name__ == '__main__':
    g = CodeParser(sys.argv[1])
    interfaces, structs = g.extract_data()
    b = GraphBuilder(interfaces, structs)
    b.resolve_interface_implementations()
