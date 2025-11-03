"""Immutable dictionary type.

The :class:`ImmutableDict` behaves like a standard :class:`dict` but blocks all
mutation operations. It can be hashed and safely used as a key where
appropriate.
"""

from functools import cached_property
from typing import Any, TypeVar


K = TypeVar("K")
V = TypeVar("V")


class ImmutableDict[K, V](dict[K, V]):
    """A hashable, immutable mapping.

    Keys and values follow the standard :class:`dict` semantics for lookup and
    iteration. Any attempt to mutate the instance raises :class:`TypeError`.
    """

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
        """Disallow clearing the mapping.

        :raises TypeError: Always, because the object is immutable.
        """
        raise TypeError("Object is immutable")

    def pop(self, *args: Any, **kwargs: Any) -> Any:
        """Disallow removing items.

        :param Any *args: Positional args accepted by :meth:`dict.pop`.
        :param Any **kwargs: Keyword args accepted by :meth:`dict.pop`.
        :return: This method never returns.
        :rtype: Any
        :raises TypeError: Always, because the object is immutable.
        """
        raise TypeError("Object is immutable")

    def popitem(self, *args: Any, **kwargs: Any) -> tuple[K, V]:
        """Disallow removing an arbitrary item.

        :param Any *args: Positional args accepted by :meth:`dict.popitem`.
        :param Any **kwargs: Keyword args accepted by :meth:`dict.popitem`.
        :return: This method never returns.
        :rtype: tuple[K, V]
        :raises TypeError: Always, because the object is immutable.
        """
        raise TypeError("Object is immutable")

    def setdefault(self, *args: Any, **kwargs: Any) -> Any:
        """Disallow setting a default value.

        :param Any *args: Positional args accepted by :meth:`dict.setdefault`.
        :param Any **kwargs: Keyword args accepted by :meth:`dict.setdefault`.
        :return: This method never returns.
        :rtype: Any
        :raises TypeError: Always, because the object is immutable.
        """
        raise TypeError("Object is immutable")

    def update(self, *args: Any, **kwargs: Any) -> None:
        """Disallow updating the mapping.

        :param Any *args: Positional args accepted by :meth:`dict.update`.
        :param Any **kwargs: Keyword args accepted by :meth:`dict.update`.
        :raises TypeError: Always, because the object is immutable.
        """
        raise TypeError("Object is immutable")
