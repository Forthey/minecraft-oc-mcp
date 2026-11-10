import types
from dataclasses import dataclass
from typing import Annotated, ClassVar, Literal, Union, get_args, get_origin, get_type_hints

NO_DEFAULT = object()

JSON_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


@dataclass(frozen=True)
class Range:
    minimum: float = None
    maximum: float = None

    def schema(self):
        return {key: value for key, value in
                (("minimum", self.minimum), ("maximum", self.maximum)) if value is not None}

    def check(self, name, value):
        if self.minimum is not None and value < self.minimum:
            return f"{name} must be >= {self.minimum}"
        if self.maximum is not None and value > self.maximum:
            return f"{name} must be <= {self.maximum}"
        return None


@dataclass(frozen=True)
class OneOf:
    values: tuple

    def schema(self):
        return {"enum": list(self.values)}

    def check(self, name, value):
        if value not in self.values:
            return f"{name} must be one of: {', '.join(map(str, self.values))}"
        return None


@dataclass(frozen=True)
class Field:
    name: str
    python_type: type
    constraints: tuple
    required: bool
    default: object = NO_DEFAULT

    def schema(self):
        result = {"type": JSON_TYPES[self.python_type]}
        for constraint in self.constraints:
            result.update(constraint.schema())
        if self.default is not NO_DEFAULT:
            result["default"] = self.default
        return result

    def check(self, value):
        if not is_instance(value, self.python_type):
            return f"{self.name} must be of type {JSON_TYPES[self.python_type]}"
        for constraint in self.constraints:
            error = constraint.check(self.name, value)
            if error:
                return error
        return None


def is_instance(value, python_type):
    if python_type is bool:
        return isinstance(value, bool)
    if python_type is float:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, python_type) and not isinstance(value, bool)


def unwrap_optional(hint):
    if get_origin(hint) in (Union, getattr(types, "UnionType", Union)):
        args = [arg for arg in get_args(hint) if arg is not type(None)]
        if len(args) == 1 and len(get_args(hint)) == 2:
            return args[0], True
    return hint, False


def collect_fields(cls):
    fields = []
    for name, hint in get_type_hints(cls, include_extras=True).items():
        if get_origin(hint) is ClassVar:
            continue
        hint, optional = unwrap_optional(hint)
        constraints = []
        if get_origin(hint) is Annotated:
            hint, *constraints = get_args(hint)
        if get_origin(hint) is Literal:
            values = get_args(hint)
            constraints.append(OneOf(values))
            hint = type(values[0])
        if hint not in JSON_TYPES:
            raise TypeError(f"{cls.__name__}.{name}: unsupported type {hint!r}")
        default = getattr(cls, name, NO_DEFAULT)
        if optional and default not in (NO_DEFAULT, None):
            raise TypeError(f"{cls.__name__}.{name}: optional field cannot have a default")
        if optional:
            default = NO_DEFAULT
        required = not optional and default is NO_DEFAULT
        fields.append(Field(name, hint, tuple(constraints), required, default))
    return fields


class Tool:
    name: ClassVar[str]
    description: ClassVar[str]
    timeout: ClassVar[float] = 30
    fields: ClassVar[list]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.fields = collect_fields(cls)

    @classmethod
    def schema(cls):
        return {
            "type": "object",
            "properties": {field.name: field.schema() for field in cls.fields},
            "required": [field.name for field in cls.fields if field.required],
        }

    @classmethod
    def prepare(cls, arguments):
        prepared = {}
        for field in cls.fields:
            value = arguments.get(field.name)
            if value is None:
                value = None if field.default is NO_DEFAULT else field.default
            if value is not None:
                prepared[field.name] = value
        return prepared

    @classmethod
    def validate(cls, arguments):
        if not isinstance(arguments, dict):
            return "arguments must be an object"
        for field in cls.fields:
            if arguments.get(field.name) is None:
                if field.required:
                    return f"{field.name} is required"
                continue
            error = field.check(arguments[field.name])
            if error:
                return error
        return None
