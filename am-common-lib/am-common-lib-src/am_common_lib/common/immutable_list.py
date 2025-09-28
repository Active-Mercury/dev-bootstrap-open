from functools import cached_property
from typing import Any, cast, Generic, TypeVar, Union


T = TypeVar("T")


class ImmutableList(list[T], Generic[T]):
    def __init__(self, elements: Any) -> None:
        super().__init__(elements)

    @cached_property
    def _hash(self) -> int:
        return hash(tuple(self))

    @cached_property
    def _str(self) -> str:
        return str(list(self))

    @cached_property
    def _repr(self) -> str:
        return f"{self.__class__.__name__}({super().__repr__()})"

    def __hash__(self) -> int:  # type: ignore[override]
        return self._hash

    def __str__(self) -> str:
        return self._str

    def __repr__(self) -> str:
        return self._repr

    def __delattr__(self, name: str) -> None:
        raise TypeError("ImmutableList is immutable")

    def __getitem__(self, index: Union[int, slice]) -> Union[T, "ImmutableList[T]"]:  # type: ignore[override]
        result = super().__getitem__(index)
        if isinstance(index, slice):
            return cast("ImmutableList[T]", ImmutableList(result))
        return cast(T, result)

    def _blocked(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError(f"{self.__class__.__name__!r} is immutable")

    # Block mutation methods
    __setattr__ = _blocked
    __setitem__ = _blocked
    __delitem__ = _blocked
    __iadd__ = _blocked  # type: ignore[assignment]
    __imul__ = _blocked  # type: ignore[assignment]
    append = _blocked
    extend = _blocked
    insert = _blocked
    pop = _blocked  # type: ignore[assignment]
    remove = _blocked
    clear = _blocked
    sort = _blocked
    reverse = _blocked
