from collections import defaultdict
import pathlib
import sys
from dataclasses import dataclass

from tree_sitter import Node, Parser, Language
from tree_sitter_go import language as golang
import pygraphviz as pgv


@dataclass
class Method:
    name: str
    params: list[str]
    returns: list[str]

    def __repr__(self):
        return f'func {self.name}({", ".join(self.params)}) ({", ".join(self.returns)})'


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


class CodeParser:
    def __init__(self, srcDir: str, debug=False):
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
                    results.append(splitted[0] if len(
                        splitted) == 1 else ''.join(splitted[1:]))
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
            if name and name.text:
                name = name.text.decode()
            if not body or not body.children or not name:
                return
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
            returns=self.normalize_named_params(
                method['returns']) if 'returns' in method else []
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
            assert (name != None)
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
                                    tname = child.child_by_field_name(
                                        'type').text.decode()
                                    if fname:
                                        fields[fname.text.decode()] = tname
                                    else:
                                        embedded.append(tname)
                            self.structs[name] = Struct(
                                name=name, fields=fields, embedded=embedded, methods=[])

    def extract_struct_methods(self, node):
        query = self.language.query('''
            (method_declaration) @mdec
            ''')
        captures = query.captures(node)
        for i in range(len(captures.get('mdec', []))):
            method_declaration = captures['mdec'][i]
            method, recv = self.parse_struct_method(method_declaration)
            self.structs[recv].methods.append(method)

    def parse_struct_method(self, node: Node) -> tuple[Method, str]:
        method = {}
        for child in node.children:
            if child.type == 'field_identifier':
                method['name'] = child.text.decode()
            elif child.type == 'parameter_list':
                text = child.text.decode()
                if 'recv' not in method:
                    method['recv'] = text.split()[-1].lstrip('*')[:-1]
                elif 'params' not in method:
                    method['params'] = text
                elif 'returns' not in method:
                    method['returns'] = text
            elif child.type == 'type_identifier':
                method['returns'] = f'({child.text.decode()})'

        return Method(
            name=method['name'],
            params=self.normalize_named_params(method['params']),
            returns=self.normalize_named_params(
                method['returns']) if 'returns' in method else []
        ), method['recv']


class GraphBuilder:
    def __init__(self, interfaces: dict[str, Interface], structs: dict[str, Struct]):
        self.interfaces = interfaces
        self.structs = structs
        self.graph: dict[str, list[str]] = defaultdict(list)

        self.resolve_interface_implementations()
        self.resolve_struct_dependencies()
        self.visualize_graph()

    def visualize_graph(self):
        G = pgv.AGraph(directed=True, strict=True)
        for i in self.structs:
            G.add_node(i)
        for i in self.interfaces:
            G.add_node(i, color="green", style="filled",
                       fillcolor="lightgreen")
        for node, edges in self.graph.items():
            for nbrs in edges:
                G.add_edge(node, nbrs)

        G.graph_attr["rankdir"] = "TB"
        G.node_attr["shape"] = "box"
        G.edge_attr["color"] = "blue"
        G.draw("type-graph.png", format="png", prog="dot")

    def resolve_interface_implementations(self):
        for struct in self.structs.values():
            for interface in self.interfaces.values():
                if struct.methods and interface.methods and self.does_implement(struct, interface):
                    self.graph[interface.name].append(struct.name)

    def resolve_struct_dependencies(self):
        for struct in self.structs.values():
            for type in struct.fields.values():
                if type in self.structs or type in self.interfaces:
                    self.graph[struct.name].append(type)

    def does_implement(self, struct: Struct, interface: Interface) -> bool:
        methods = {m.name: m for m in struct.methods}

        # add methods of embedded structs
        if struct.embedded:
            for emb_struct in struct.embedded:
                assert (emb_struct in self.structs)
                for m in self.structs[emb_struct].methods:
                    methods[m.name] = m

        for imethod in interface.methods:
            if imethod.name not in methods:
                return False
            method = methods[imethod.name]
            if not self.compare_methods(imethod, method):
                return False
        return True

    def compare_methods(self, a: Method, b: Method) -> bool:
        return a.name == b.name and tuple(a.params) == tuple(b.params) and tuple(a.returns) == tuple(b.returns)


if __name__ == '__main__':
    g = CodeParser(sys.argv[1])
    interfaces, structs = g.extract_data()
    b = GraphBuilder(interfaces, structs)
