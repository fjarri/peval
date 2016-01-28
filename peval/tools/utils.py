import ast
import re


def unindent(source):
    """
    Shift source to the left so that it starts with zero indentation.
    """
    source = source.rstrip("\n ").lstrip("\n")
    indent = re.match(r"([ \t])*", source).group(0)
    lines = source.split("\n")
    shifted_lines = []
    for line in lines:
        line = line.rstrip()
        if len(line) > 0:
            if not line.startswith(indent):
                raise ValueError("Inconsistent indent at line " + repr(line))
            shifted_lines.append(line[len(indent):])
        else:
            shifted_lines.append(line)
    return "\n".join(shifted_lines)


def replace_fields(node, **kwds):
    """
    Return a node with several of its fields replaced by the given values.
    """
    new_kwds = dict(ast.iter_fields(node))
    for key, value in kwds.items():
        if value is not new_kwds[key]:
            break
    else:
        return node
    new_kwds.update(kwds)
    return type(node)(**new_kwds)


def ast_equal(node1, node2):
    """
    Test two AST nodes or two lists of AST nodes for equality.
    """
    if node1 is node2:
        return True

    if type(node1) != type(node2):
        return False

    if type(node1) == list:
        if len(node1) != len(node2):
            return False
        for elem1, elem2 in zip(node1, node2):
            if not ast_equal(elem1, elem2):
                return False
    elif isinstance(node1, ast.AST):
        for attr, value1 in ast.iter_fields(node1):
            value2 = getattr(node2, attr)
            if not ast_equal(value1, value2):
                return False
    else:
        if node1 != node2:
            return False

    return True


def map_accum(func, acc, container, *args):
    if container is None:
        return acc, None
    elif type(container) in (list, tuple, zip):
        new_container = []
        for elem in container:
            acc, new_elem = map_accum(func, acc, elem, *args)
            new_container.append(new_elem)
        container_type = type(container)
        result_type = list if container_type == zip else container_type
        return acc, result_type(new_container)
    elif type(container) == dict:
        new_container = dict(container)
        for key, elem in new_container.items():
            acc, new_container[key] = map_accum(func, acc, elem, *args)
        return acc, new_container
    else:
        return func(acc, container, *args)


def fold_and(func, container):
    if type(container) in (list, tuple, zip):
        return all(fold_and(func, elem) for elem in container)
    elif type(container) == dict:
        return all(fold_and(func, elem) for elem in container.values())
    else:
        return func(container)
