def get_not_overridden_attributes(cls: type, base_cls: type) -> set[str]:
    not_overridden = set(dir(base_cls))

    for attr_name in dir(base_cls):
        try:
            base_attr = getattr(base_cls, attr_name)
            cls_attr = getattr(cls, attr_name)

            if base_attr is not cls_attr:
                not_overridden.remove(attr_name)
        except (AttributeError, TypeError):
            continue

    return not_overridden
