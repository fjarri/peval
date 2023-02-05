import ast
from typing import Set, List, Optional, Union


class Node:
    def __init__(self, ast_node: ast.AST) -> None:
        self.ast_node = ast_node
        self.parents = set()
        self.children = set()


class Graph:
    def __init__(self) -> None:
        self.nodes = {}

    def add_node(self, ast_node: ast.AST) -> int:
        node_id = id(ast_node)
        self.nodes[node_id] = Node(ast_node)
        return node_id

    def add_edge(self, src: int, dest: int) -> None:
        assert src in self.nodes
        assert dest in self.nodes

        # assert dest not in self.children_of(src)
        # assert src not in self.parents_of(dest)

        self.nodes[src].children.add(dest)
        self.nodes[dest].parents.add(src)

    def children_of(self, node: int) -> Set[int]:
        return self.nodes[node].children

    def parents_of(self, node: int) -> Set[int]:
        return self.nodes[node].parents

    def update(self, other: "Graph") -> None:
        for node in other.nodes:
            assert node not in self.nodes
        self.nodes.update(other.nodes)

    def get_nontrivial_nodes(self) -> List[int]:
        # returns ids of nodes that can possibly raise an exception
        nodes = []
        for node_id, node_obj in self.nodes.items():
            node = node_obj.ast_node
            if type(node) not in (ast.Break, ast.Continue, ast.Pass, ast.Try):
                nodes.append(node_id)
        return nodes


class Jumps:
    def __init__(
        self,
        returns: Optional[List[int]] = None,
        breaks: Optional[List[int]] = None,
        continues=None,
        raises=None,
    ) -> None:
        self.returns = [] if returns is None else returns
        self.breaks = [] if breaks is None else breaks
        self.continues = [] if continues is None else continues
        self.raises = [] if raises is None else raises

    def join(self, other: "Jumps") -> "Jumps":
        return Jumps(
            returns=self.returns + other.returns,
            breaks=self.breaks + other.breaks,
            continues=self.continues + other.continues,
            raises=self.raises + other.raises,
        )


class ControlFlowSubgraph:
    def __init__(
        self,
        graph: Graph,
        enter: int,
        exits: Optional[List[int]] = None,
        jumps: Optional[Jumps] = None,
    ) -> None:
        self.graph = graph
        self.enter = enter
        self.exits = [] if exits is None else exits
        self.jumps = Jumps() if jumps is None else jumps


class ControlFlowGraph:
    def __init__(
        self,
        graph: Graph,
        enter: int,
        exits: Optional[List[int]] = None,
        raises=None,
    ) -> None:
        self.graph = graph
        self.enter = enter
        self.exits = [] if exits is None else exits
        self.raises = [] if raises is None else raises


def _build_if_cfg(node: ast.If) -> ControlFlowSubgraph:
    cfg_true = _build_cfg(node.body)
    exits = cfg_true.exits
    jumps = cfg_true.jumps
    graph = cfg_true.graph

    node_id = graph.add_node(node)

    graph.add_edge(node_id, cfg_true.enter)

    if len(node.orelse) > 0:
        cfg_false = _build_cfg(node.orelse)
        exits += cfg_false.exits
        jumps = jumps.join(cfg_false.jumps)
        graph.update(cfg_false.graph)
        graph.add_edge(node_id, cfg_false.enter)
    else:
        exits.append(node_id)

    return ControlFlowSubgraph(graph, node_id, exits=exits, jumps=jumps)


def _build_loop_cfg(node: Union[ast.For, ast.While]) -> ControlFlowSubgraph:
    cfg = _build_cfg(node.body)
    graph = cfg.graph

    node_id = graph.add_node(node)

    graph.add_edge(node_id, cfg.enter)

    for c_id in cfg.jumps.continues:
        graph.add_edge(c_id, node_id)
    exits = cfg.jumps.breaks
    jumps = Jumps(raises=cfg.jumps.raises)

    for exit_ in cfg.exits:
        graph.add_edge(exit_, node_id)

    if len(node.orelse) == 0:
        exits += cfg.exits
    else:
        cfg_orelse = _build_cfg(node.orelse)

        graph.update(cfg_orelse.graph)
        exits += cfg_orelse.exits
        jumps = jumps.join(Jumps(raises=cfg_orelse.jumps.raises))
        for exit_ in cfg.exits:
            graph.add_edge(exit_, cfg_orelse.enter)

    return ControlFlowSubgraph(graph, node_id, exits=exits, jumps=jumps)


def _build_with_cfg(node: ast.With) -> ControlFlowSubgraph:
    cfg = _build_cfg(node.body)
    graph = cfg.graph

    node_id = graph.add_node(node)

    graph.add_edge(node_id, cfg.enter)
    return ControlFlowSubgraph(graph, node_id, exits=cfg.exits, jumps=cfg.jumps)


def _build_break_cfg(node: ast.Break) -> ControlFlowSubgraph:
    graph = Graph()
    node_id = graph.add_node(node)
    return ControlFlowSubgraph(graph, node_id, jumps=Jumps(breaks=[node_id]))


def _build_continue_cfg(node):
    graph = Graph()
    node_id = graph.add_node(node)
    return ControlFlowSubgraph(graph, node_id, jumps=Jumps(continues=[node_id]))


def _build_return_cfg(node: ast.Return) -> ControlFlowSubgraph:
    graph = Graph()
    node_id = graph.add_node(node)
    return ControlFlowSubgraph(graph, node_id, jumps=Jumps(returns=[node_id]))


def _build_statement_cfg(node: ast.stmt) -> ControlFlowSubgraph:
    graph = Graph()
    node_id = graph.add_node(node)
    return ControlFlowSubgraph(graph, node_id, exits=[node_id])


def _build_excepthandler_cfg(node: ast.ExceptHandler) -> ControlFlowSubgraph:
    graph = Graph()
    enter = graph.add_node(node)

    cfg = _build_cfg(node.body)
    graph.update(cfg.graph)
    graph.add_edge(enter, cfg.enter)

    return ControlFlowSubgraph(graph, enter, exits=cfg.exits, jumps=cfg.jumps)


def _build_try_block_cfg(
    try_node: ast.Try,
    body: List[ast.AST],
    handlers: List[ast.ExceptHandler],
    orelse: List[ast.AST],
) -> ControlFlowSubgraph:
    graph = Graph()
    enter = graph.add_node(try_node)

    body_cfg = _build_cfg(body)

    jumps = body_cfg.jumps
    jumps.raises = []  # raises will be connected to all the handlers anyway

    graph.update(body_cfg.graph)
    graph.add_edge(enter, body_cfg.enter)

    handler_cfgs = [_build_excepthandler_cfg(handler) for handler in handlers]
    for handler_cfg in handler_cfgs:
        graph.update(handler_cfg.graph)
        jumps = jumps.join(handler_cfg.jumps)

    # FIXME: is it correct in case of nested `try`s?
    body_ids = body_cfg.graph.get_nontrivial_nodes()
    if len(handler_cfgs) > 0:
        # FIXME: if there are exception handlers,
        # assuming that all the exceptions are caught by them
        for body_id in body_ids:
            for handler_cfg in handler_cfgs:
                graph.add_edge(body_id, handler_cfg.enter)
    else:
        # If there are no handlers, every statement can potentially raise
        # (otherwise they wouldn't be in a try block)
        jumps = jumps.join(Jumps(raises=body_ids))

    exits = body_cfg.exits

    if len(orelse) > 0 and len(body_cfg.exits) > 0:
        # FIXME: show warning about unreachable code if there's `orelse`, but no exits from body?
        orelse_cfg = _build_cfg(orelse)
        graph.update(orelse_cfg.graph)
        jumps = jumps.join(orelse_cfg.jumps)
        for exit_ in exits:
            graph.add_edge(exit_, orelse_cfg.enter)
        exits = orelse_cfg.exits

    for handler_cfg in handler_cfgs:
        exits += handler_cfg.exits

    return ControlFlowSubgraph(graph, enter, exits=exits, jumps=jumps)


def _build_try_finally_block_cfg(
    try_node: ast.Try,
    body: List[ast.AST],
    handlers: List[ast.ExceptHandler],
    orelse: List[ast.AST],
    finalbody: List[ast.AST],
) -> ControlFlowSubgraph:
    try_cfg = _build_try_block_cfg(try_node, body, handlers, orelse)

    if len(finalbody) == 0:
        return try_cfg

    # everything has to pass through finally
    final_cfg = _build_cfg(finalbody)
    graph = try_cfg.graph
    jumps = try_cfg.jumps
    graph.update(final_cfg.graph)

    for exit_ in try_cfg.exits:
        graph.add_edge(exit_, final_cfg.enter)

    def pass_through(jump_list):
        if len(jump_list) > 0:
            for jump_id in jump_list:
                graph.add_edge(jump_id, final_cfg.enter)
            return final_cfg.exits
        else:
            return []

    returns = pass_through(jumps.returns)
    raises = pass_through(jumps.raises)
    continues = pass_through(jumps.continues)
    breaks = pass_through(jumps.breaks)

    return ControlFlowSubgraph(
        graph,
        try_cfg.enter,
        exits=final_cfg.exits,
        jumps=Jumps(returns=returns, raises=raises, continues=continues, breaks=breaks),
    )


def _build_try_finally_cfg(node):
    # If there are no exception handlers, the body is just a sequence of statements
    return _build_try_finally_block_cfg(node, node.body, [], [], node.finalbody)


def _build_try_cfg(node: ast.Try) -> ControlFlowSubgraph:
    return _build_try_finally_block_cfg(node, node.body, node.handlers, node.orelse, node.finalbody)


def _build_node_cfg(node) -> ControlFlowSubgraph:
    handlers = {
        ast.If: _build_if_cfg,
        ast.For: _build_loop_cfg,
        ast.While: _build_loop_cfg,
        ast.With: _build_with_cfg,
        ast.Break: _build_break_cfg,
        ast.Continue: _build_continue_cfg,
        ast.Return: _build_return_cfg,
        ast.Try: _build_try_cfg,
    }

    if type(node) in handlers:
        handler = handlers[type(node)]
    else:
        handler = _build_statement_cfg

    return handler(node)


def _build_cfg(statements) -> ControlFlowSubgraph:
    enter = id(statements[0])

    exits = [enter]
    graph = Graph()

    jumps = Jumps()

    for i, node in enumerate(statements):
        cfg = _build_node_cfg(node)

        graph.update(cfg.graph)

        if i > 0:
            for exit_ in exits:
                graph.add_edge(exit_, cfg.enter)

        exits = cfg.exits
        jumps = jumps.join(cfg.jumps)

        if type(node) in (ast.Break, ast.Continue, ast.Return):
            # Issue a warning about unreachable code?
            break

    return ControlFlowSubgraph(graph, enter, exits=exits, jumps=jumps)


def build_cfg(statements) -> ControlFlowGraph:
    cfg = _build_cfg(statements)
    assert len(cfg.jumps.breaks) == 0
    assert len(cfg.jumps.continues) == 0
    return ControlFlowGraph(
        cfg.graph, cfg.enter, cfg.exits + cfg.jumps.returns, raises=cfg.jumps.raises
    )
