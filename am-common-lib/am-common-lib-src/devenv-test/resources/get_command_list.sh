(
  IFS=':'
  find $PATH -maxdepth 1 -mindepth 1 \( -type f -o -type l \) \
    -printf '%f\n'
) | sort -u
