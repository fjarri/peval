import sys
import ast
import typing

ConstsDictT = typing.Dict[str, typing.Any]
PassOutputT = typing.Tuple[ast.AST, ConstsDictT]

NodeTypeT = typing.Type[ast.AST]
NodeTypeIsInstanceCriteriaT = typing.Union[typing.Tuple[NodeTypeT], NodeTypeT]

NameNodeT = typing.Union[ast.arg, ast.Name]

ConstantNodeT = ast.Constant

ConstantOrNameNodeT = typing.Union[ConstantNodeT, ast.Name]

ConstantT = typing.Union[int, float, complex, str, bytes, bool]
ConsantOrASTNodeT = typing.Union[ConstantT, ast.AST]
