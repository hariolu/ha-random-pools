# All comments in English.
DOMAIN = "pools"

# Config keys
CONF_DIRECTORY = "directory"              # for text pools
CONF_POOLS = "pools"
CONF_SOUNDS_DIRECTORY = "sounds_directory"
CONF_SOUND_POOLS = "sound_pools"
CONF_URL_MODE = "url_mode"               # 'auto' | 'local' | 'media' | 'none'

# Defaults (component-root friendly, but customizable)
DEFAULT_DIRECTORY = "custom_components/pools/assets/text"
DEFAULT_SOUNDS_DIRECTORY = "custom_components/pools/assets/sounds"
DEFAULT_URL_MODE = "auto"

# Limits
MAX_LINES = 255
MAX_CHARS = 255

# Common attributes
ATTR_FILE = "file"
ATTR_LINE_COUNT = "line_count"
ATTR_TRUNCATED_LINES = "truncated_lines"
ATTR_IGNORED_BLANK = "ignored_blank"
ATTR_LAST_INDEX = "last_index"
ATTR_FILE_MTIME = "file_mtime"

# Diagnostics (both text & sounds)
ATTR_SHUFFLE_COUNT = "shuffle_count"
ATTR_RELOAD_COUNT = "reload_count"
ATTR_LAST_SHUFFLE = "last_shuffle"
ATTR_LAST_RELOAD = "last_reload"

# Sound attributes
ATTR_DIR = "dir"
ATTR_FILE_COUNT = "file_count"
ATTR_LAST_FILE = "last_file"
ATTR_RELATIVE_URL = "relative_url"
ATTR_DIR_MTIME = "dir_mtime"
