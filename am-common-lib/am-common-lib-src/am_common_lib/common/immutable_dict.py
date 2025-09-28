from functools import cached_property
from typing import Any, Generic, TypeVar


K = TypeVar("K")
V = TypeVar("V")


class ImmutableDict(dict[K, V], Generic[K, V]):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

    @cached_property
    def _hash(self) -> int:
        return hash(frozenset(self.items()))

    def __hash__(self) -> int:  # type: ignore[override]
        return self._hash

    def __setitem__(self, key: K, value: V) -> None:
        raise TypeError("Object is immutable")

    def __delitem__(self, key: K) -> None:
        raise TypeError("Object is immutable")

    @cached_property
    def _str(self) -> str:
        return dict.__repr__(self)

    def __str__(self) -> str:
        return self._str

    @cached_property
    def _repr(self) -> str:
        return f"{self.__class__.__name__}({super().__repr__()})"

    def __repr__(self) -> str:
        return self._repr

    def clear(self) -> None:
        raise TypeError("Object is immutable")

    def pop(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("Object is immutable")

    def popitem(self, *args: Any, **kwargs: Any) -> tuple[K, V]:
        raise TypeError("Object is immutable")

    def setdefault(self, *args: Any, **kwargs: Any) -> Any:
        raise TypeError("Object is immutable")

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("Object is immutable")
