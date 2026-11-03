"""R-1 limits."""

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_CELLS = 1_000_000
# A zip bomb guard, not a product limit: well above what 25 MB of real workbook inflates to.
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
CONVERT_TIMEOUT_SECONDS = 180
